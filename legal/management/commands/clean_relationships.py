from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from ...models import LegalRelationship, RelationshipType

class Command(BaseCommand):
    help = "Clean and reconcile extracted legal relationships."

    SUPERSEDING_CONFLICT_TYPES = {
        RelationshipType.TAKHSIS,
        RelationshipType.TAQYID,
        RelationshipType.TAKHASSOS,
        RelationshipType.HOKUMAT,
        RelationshipType.REPEALS,
        RelationshipType.CANCELS,
        RelationshipType.ANNULS,
        RelationshipType.EXPIRES,
        RelationshipType.IDENTICAL,
    }

    # (weaker, stronger)
    PRIORITY_RULES = {
        (
            RelationshipType.TAKHSIS,
            RelationshipType.TAQYID,
        ): "REMOVE_BOTH",

        (
            RelationshipType.TAQYID,
            RelationshipType.HOKUMAT,
        ): "REMOVE_WEAKER",
        (
            RelationshipType.AMENDS,
            RelationshipType.REPLACES,
        ): "REMOVE_WEAKER",
        (
            RelationshipType.REPEALS,
            RelationshipType.REMOVES,
        ): "REMOVE_WEAKER",
        (
            RelationshipType.CANCELS,
            RelationshipType.ANNULS,
        ): "REMOVE_WEAKER",
    }


    def remove_priority_conflicts(self, relations, to_delete, reasons):
        types = {r.relationship_type: r for r in relations if r.id not in to_delete}
        for (weak, strong), action in self.PRIORITY_RULES.items():
            if weak in types and strong in types:
                weak_rel = types[weak]
                strong_rel = types[strong]
                if action == "REMOVE_BOTH":
                    to_delete.add(weak_rel.id)
                    to_delete.add(strong_rel.id)
                    reasons[f"remove_both_{weak}_{strong}"] += 1
                elif action == "REMOVE_WEAKER":
                    to_delete.add(weak_rel.id)
                    reasons[f"{weak}_removed_by_{strong}"] += 1


    @transaction.atomic
    def handle(self, *args, **options):
        relationships = list(LegalRelationship.objects.select_related("source", "target").all())
        before_count = len(relationships)
        if not relationships:
            self.stdout.write(self.style.WARNING("No legal relationships found."))
            return

        to_delete = set()
        removal_reasons = Counter()
        for relationship in relationships:
            if relationship.source_id == relationship.target_id:
                to_delete.add(relationship.id)
                removal_reasons["self_relation"] += 1

        relationship_index = {}
        for relationship in relationships:
            key = (relationship.source_id, relationship.target_id)
            relationship_index.setdefault(key, []).append(relationship)
        for key, relations in relationship_index.items():
            active_relations = [r for r in relations if r.id not in to_delete]
            if not active_relations:
                continue

            self.remove_priority_conflicts(active_relations, to_delete, removal_reasons)
            conflict = None
            stronger_relations = []
            for relationship in active_relations:
                if relationship.id in to_delete:
                    continue
                if relationship.relationship_type == RelationshipType.CONFLICTS:
                    conflict = relationship
                elif relationship.relationship_type in self.SUPERSEDING_CONFLICT_TYPES:
                    stronger_relations.append(relationship)

            if conflict and stronger_relations:
                to_delete.add(conflict.id)
                for relationship in stronger_relations:
                    removal_reasons[f"conflict_superseded_by_{relationship.relationship_type}"] += 1
        if to_delete:
            LegalRelationship.objects.filter(id__in=to_delete).delete()

        after_count = before_count - len(to_delete)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Relationship cleanup completed."))
        self.stdout.write("")
        self.stdout.write(f"Relationships before cleanup: {before_count}")
        self.stdout.write(f"Relationships removed: {len(to_delete)}")
        self.stdout.write(f"Relationships after cleanup: {after_count}")
        if removal_reasons:
            self.stdout.write("")
            self.stdout.write("Removal details:")
            for reason, count in sorted(removal_reasons.items()):
                self.stdout.write(f"  {reason}: {count}")
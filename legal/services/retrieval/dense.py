import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from legal.models import ElementType, LegalElement, LegalProvision, StructuralElement
from .logging import write_last_query_log

load_dotenv()

MILVUS_HOST = "127.0.0.1"
MILVUS_PORT = 19530

COLLECTION_NAME = "legal_provisions"

INDEX_BATCH_SIZE = 128
ENCODE_BATCH_SIZE = 32

def resolve_local_model_path(model_path):
    if not model_path:
        return None

    candidate = Path(model_path).expanduser()
    if not candidate.exists():
        return str(candidate)

    if candidate.is_file() and candidate.name == "config.json":
        return str(candidate.parent)

    if candidate.is_dir():
        if (candidate / "config.json").exists():
            return str(candidate)

        snapshots_dir = candidate / "snapshots"
        if snapshots_dir.is_dir():
            snapshot_dirs = sorted([path for path in snapshots_dir.iterdir() if path.is_dir()], key=lambda path: path.name)

            for snapshot_dir in snapshot_dirs:
                if (snapshot_dir / "config.json").exists():
                    return str(snapshot_dir)

    return str(candidate)


class EmbeddingModel:
    MODEL_NAME = "PartAI/Tooka-SBERT-V2-Large"
    def __init__(self, device=None):
        default_model_path = Path(__file__).resolve().parents[3] / "Embedder model"
        resolved_model_path = resolve_local_model_path(os.getenv("EMBEDDING_MODEL_PATH") or str(default_model_path))
        self.model = SentenceTransformer(resolved_model_path, device=device, local_files_only=True)
        print(f"Embedding model: {self.model}")
        print(f"Embedding dimension: {self.dimension}")

    def encode(self, texts, normalize=True, batch_size=ENCODE_BATCH_SIZE):
        return self.model.encode(texts, batch_size=batch_size, normalize_embeddings=normalize, show_progress_bar=False, convert_to_numpy=True, device=self.model.device)

    def encode_query(self, text):
        return self.encode([f"سوال: {text}"])[0]

    def encode_document(self, text):
        return self.encode([f"متن: {text}"])[0]

    @property
    def dimension(self):
        return self.model.get_embedding_dimension()


class DenseIndexer:
    COLLECTION_NAME = COLLECTION_NAME

    PROVISION_TYPE_LABELS = {
        "constitutional_principle": "اصل",
        "article": "ماده",
        "note": "تبصره",
        "clause": "بند",
        "subclause": "جزء",
        "item": "جزء",
        "other": "مقرره",
    }

    STRUCTURAL_TYPE_LABELS = {
        "book": "کتاب",
        "part": "بخش",
        "chapter": "فصل",
        "section": "مبحث",
        "subsection": "گفتار",
        "introduction": "مقدمه",
        "other": "بخش",
    }

    def __init__(self, embedding_model, batch_size=INDEX_BATCH_SIZE, encode_batch_size=ENCODE_BATCH_SIZE):
        self.embedding_model = embedding_model
        self.batch_size = batch_size
        self.encode_batch_size = encode_batch_size
        self.collection = None

    def connect(self):
        connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT,)

    def create_collection(self):
        if self.collection is not None:
            return

        if utility.has_collection(self.COLLECTION_NAME):
            self.collection = Collection(self.COLLECTION_NAME)
            return

        fields = [
            FieldSchema(name="provision_id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_model.dimension),
            FieldSchema(name="provision_ids", dtype=DataType.VARCHAR, max_length=65535),
        ]
        
        schema = CollectionSchema(fields=fields, description=("Dense embeddings of legal provision groups"))
        self.collection = Collection(name=self.COLLECTION_NAME, schema=schema,)
        self.collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": "AUTOINDEX",
                "metric_type": "COSINE",
                "params": {},
            })

    def _get_queryset(self):
        return LegalProvision.objects.select_related("element__document").order_by("id")

    def _to_persian_digits(self, value):
        if value is None:
            return ""

        return str(value).translate(
            str.maketrans(
                "0123456789٠١٢٣٤٥٦٧٨٩",
                "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹",
            )
        )

    def _get_provision_type_label(self, provision):
        return self.PROVISION_TYPE_LABELS.get(provision.provision_type, "مقرره")

    def _get_structural_type_label(self, structural):
        return self.STRUCTURAL_TYPE_LABELS.get(structural.structural_type, "بخش")

    def _build_groups(self):
        provisions = list(self._get_queryset())
        elements = list(LegalElement.objects.only("id", "parent_id", "element_type").order_by("id"))

        parent_by_element_id = {element.id: element.parent_id for element in elements}
        element_type_by_id = {element.id: element.element_type for element in elements}
        provision_by_element_id = {provision.element_id: provision for provision in provisions}
        groups = defaultdict(list)
        root_cache = {}

        def get_root_element_id(element_id):
            if element_id in root_cache:
                return root_cache[element_id]

            path = []
            current_id = element_id
            while current_id is not None:
                if current_id in root_cache:
                    root_id = root_cache[current_id]
                    break

                path.append(current_id)
                parent_id = parent_by_element_id.get(current_id)
                if parent_id is None:
                    root_id = current_id
                    break

                parent_type = element_type_by_id.get(parent_id)
                if parent_type == ElementType.STRUCTURAL:
                    root_id = current_id
                    break

                current_id = parent_id
            for path_element_id in path:
                root_cache[path_element_id] = root_id
            return root_id

        for provision in provisions:
            root_element_id = get_root_element_id(provision.element_id)
            root_provision = provision_by_element_id.get(root_element_id)
            if root_provision is None:
                continue
            groups[root_provision.id].append(provision)
            
        for root_id, group in groups.items():
            root = next((provision for provision in group if provision.id == root_id), None)
            if root is not None:
                groups[root_id] = [root, *(provision for provision in group if provision.id != root_id)]
                
        return groups, parent_by_element_id

    def _build_provision_text(self, provision):
        provision_type = self._get_provision_type_label(provision)
        number = self._to_persian_digits(provision.number).strip()
        title = provision.title.strip() if provision.title else ""
        text = provision.text.strip() if provision.text else ""
        prefix = f"{provision_type} {number}".strip()
        parts = [prefix]
        if title:
            parts.append(title)
            
        if text:
            parts.append(text)
            
        return ": ".join(parts)

    def _build_structural_text(self, provision, parent_by_element_id, structural_by_element_id,):
        parts = []
        current_id = provision.element_id
        while current_id is not None:
            parent_id = parent_by_element_id.get(current_id)
            if parent_id is None:
                break
            
            structural = structural_by_element_id.get(parent_id)
            if structural is not None:
                structural_type = self._get_structural_type_label(structural)
                number = self._to_persian_digits(structural.number).strip()
                title = structural.title.strip() if structural.title else ""
                if number and title:
                    parts.append(f"{structural_type} {number}: {title}")
                elif number:
                    parts.append(f"{structural_type} {number}")
                elif title:
                    parts.append(f"{structural_type}: {title}")
                    
            current_id = parent_id
            
        parts.reverse()
        return " ".join(parts)

    def _build_root_text(self, root_provision, parent_by_element_id, structural_by_element_id,):
        provision_type = self._get_provision_type_label(root_provision)
        number = self._to_persian_digits(root_provision.number).strip()
        title = root_provision.title.strip() if root_provision.title else ""
        text = root_provision.text.strip() if root_provision.text else ""
        parts = [f"{provision_type} {number}".strip()]
        if title:
            parts.append(title)
        
        structural_text = self._build_structural_text(root_provision, parent_by_element_id, structural_by_element_id)
        if structural_text:
            parts.append(structural_text)
        
        document = root_provision.element.document
        if document.title:
            parts.append(document.title.strip())
        
        if text:
            parts.append(text)
        
        return ": ".join(parts)

    def _get_text(self, provisions, parent_by_element_id, structural_by_element_id):
        if not provisions:
            return ""

        root_provision = provisions[0]
        parts = [self._build_root_text(root_provision, parent_by_element_id, structural_by_element_id,)]
        parts.extend(self._build_provision_text(provision) for provision in provisions[1:])
        return "\n".join(parts)

    def _index_batch(self, groups, parent_by_element_id, structural_by_element_id):
        texts = []
        ids = []
        provision_ids = []
        for root_id, provisions in groups:
            ids.append(root_id)
            text = self._get_text(provisions, parent_by_element_id, structural_by_element_id)
            texts.append(f"متن: {text}")
            provision_ids.append(json.dumps([provision.id for provision in provisions]))

        embeddings = self.embedding_model.encode(texts, batch_size=self.encode_batch_size)
        self.collection.upsert([ids, embeddings.tolist(), provision_ids, ])
        return len(ids)

    def index(self, provisions):
        self.create_collection()
        provisions = list(provisions)
        if not provisions:
            return 0
        
        groups, parent_by_element_id = self._build_groups()
        structural_elements = list(StructuralElement.objects.only("element_id", "structural_type", "number", "title"))
        structural_by_element_id = {structural.element_id: structural for structural in structural_elements}
        selected_ids = {provision.id for provision in provisions}
        selected_groups = [(root_id, group_provisions) for root_id, group_provisions in groups.items() if any(provision.id in selected_ids for provision in group_provisions)]
        
        total_indexed = 0
        for start in range(0, len(selected_groups), self.batch_size):
            batch = selected_groups[start : start + self.batch_size]
            total_indexed += self._index_batch(batch, parent_by_element_id, structural_by_element_id)
        
        self.collection.flush()
        return total_indexed

    def index_provisions(self, provision_ids):
        provisions = LegalProvision.objects.filter(id__in=provision_ids).order_by("id")
        return self.index(provisions)

    def index_all(self):
        self.create_collection()
        groups, parent_by_element_id = self._build_groups()
        groups = list(groups.items())

        structural_elements = list(StructuralElement.objects.only("element_id", "structural_type", "number", "title"))
        structural_by_element_id = {structural.element_id: structural for structural in structural_elements}
        
        total_indexed = 0
        total_count = len(groups)
        print(f"Starting dense indexing: {total_count} provision groups")
        for start in range(0, total_count, self.batch_size):
            batch = groups[start : start + self.batch_size]
            count = self._index_batch(batch, parent_by_element_id, structural_by_element_id)
            total_indexed += count
            print(f"Indexed {total_indexed}/{total_count}")
        
        self.collection.flush()
        print(f"Finished dense indexing: {total_indexed} provision groups")
        return total_indexed


class DenseRetriever:
    COLLECTION_NAME = COLLECTION_NAME

    def __init__(self, embedding_model):
        self.embedding_model = embedding_model
        self.collection = None

    def connect(self):
        connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
        self.collection = Collection(self.COLLECTION_NAME)
        self.collection.load()

    def search(self, query, top_k=30):
        if self.collection is None:
            raise RuntimeError("DenseRetriever is not connected.")
        query_vector = self.embedding_model.encode_query(query)
        search_results = self.collection.search(
            data=[query_vector.tolist()],
            anns_field="embedding",
            param={
                "metric_type": "COSINE",
                "params": {},
            },
            limit=top_k,
            output_fields=[
                "provision_id",
                "provision_ids",
            ])
        
        hits = search_results[0]
        if not hits:
            return []
        
        root_ids = [int(hit.id) for hit in hits]
        group_provision_ids = {}
        for hit in hits:
            provision_ids = json.loads(hit.entity.get("provision_ids"))
            group_provision_ids[int(hit.id)] = provision_ids
        
        all_provision_ids = set()
        for provision_ids in group_provision_ids.values():
            all_provision_ids.update(provision_ids)

        provisions = LegalProvision.objects.select_related("element__document").filter(id__in=all_provision_ids)
        provisions_by_id = {provision.id: provision for provision in provisions}
        
        results = []
        for root_id, hit in zip(root_ids, hits):
            provision_ids = group_provision_ids[root_id]
            group_provisions = [provisions_by_id[provision_id] for provision_id in provision_ids if provision_id in provisions_by_id]
            root_provision = provisions_by_id.get(root_id)
            if root_provision is None:
                continue
            results.append({
                    "provision": root_provision,
                    "score": hit.distance,
                    "children": group_provisions,
                })

        try:
            write_last_query_log("dense", query, results)
        except Exception:
            pass

        return results

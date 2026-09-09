class ContextBuilder:
    def __init__(self, max_results=10):
        self.max_results = max_results

    def build(self, results):
        if not results:
            return ""

        results = results[: self.max_results]
        context_parts = []

        for index, result in enumerate(results, start=1):
            root = result["provision"]
            provisions = result.get("children", [root])

            document = root.element.document

            parts = [
                f"[{index}] سند: {document.title}"
            ]

            for provision in provisions:
                provision_parts = []

                if provision.number:
                    provision_parts.append(
                        f"{provision.provision_type} {provision.number}"
                    )

                if provision.title:
                    provision_parts.append(
                        f"عنوان: {provision.title}"
                    )

                if provision.text:
                    provision_parts.append(
                        f"متن: {provision.text}"
                    )

                if provision_parts:
                    parts.append("\n".join(provision_parts))

            context_parts.append("\n".join(parts))

        return "\n\n---\n\n".join(context_parts)

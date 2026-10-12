from ..config import Settings
from ..rag.index import DocumentIndex
from .base import Tool, ToolContext, untrusted


class DocumentSearchTool(Tool):
    def __init__(self, settings: Settings, index: DocumentIndex):
        super().__init__(
            name="search_company_documents",
            label="Searching company documents",
            kind="documents",
            description=(
                "Search Enfactum's internal knowledge base (policies, handbooks, SOPs, manuals, process docs, "
                "uploaded files). Only returns documents the current employee is allowed to read. Use for any "
                "question about how Enfactum works, its rules, benefits, procedures or internal documentation."
            ),
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string",
                                         "description": "Standalone search query with the key terms of the question."}},
                "required": ["query"],
            },
        )
        self.s = settings
        self.index = index

    def status_text(self, args: dict) -> str:
        return f"Searching company documents for \u201c{args.get('query', '')}\u201d"

    async def run(self, args: dict, ctx: ToolContext) -> str:
        query = str(args.get("query", "")).strip()[:500]
        hits = await self.index.search(query, ctx.user, k=self.s.rag_top_k)
        if not hits:
            return ("No accessible company documents matched. Either the information is not in the knowledge base "
                    "or the user does not have access to it. Do not guess.")
        blocks = []
        for h in hits:
            page = f", p. {h.page}" if h.page else ""
            n = ctx.citations.add(kind="document", title=f"{h.title}{page}", key=f"doc:{h.document_id}:{h.page}",
                                  snippet=h.text[:300])
            blocks.append(f"[{n}] {h.title}{page}\n{h.text}")
        return untrusted("company_documents", "\n\n---\n\n".join(blocks))

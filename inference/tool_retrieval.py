import json
import requests
from typing import Union, List, Dict, Optional
from qwen_agent.tools.base import BaseTool, register_tool


@register_tool("retrieval", allow_overwrite=True)
class Retrieval(BaseTool):
    name = "retrieval"
    description = "Unified retrieval interface that searches knowledge base and returns relevant documents with similarity scores."
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question or query to search for in the knowledge base"
            },
            "dataset_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Dataset IDs to search in",
                "default": ["1c9c4d369ce411f093700242ac170006"]
            },
            "document_ids": {
                "type": "array", 
                "items": {"type": "string"},
                "description": "Document IDs to search in",
                "default": []
            },
            "similarity_threshold": {
                "type": "number",
                "description": "Minimum similarity threshold for results",
                "default": 0.6
            },
            "vector_similarity_weight": {
                "type": "number", 
                "description": "Weight for vector similarity",
                "default": 0.7
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top results to return",
                "default": 4
            },
            "keyword": {
                "type": "boolean",
                "description": "Whether to use keyword search",
                "default": False
            },
            "highlight": {
                "type": "boolean",
                "description": "Whether to use highlight",
                "default": False
            },
            "cross_languages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Cross language search support",
                "default": ["ch", "en"]
            }
        },
        "required": ["question"]
    }

    def __init__(self, cfg: Optional[dict] = None):
        super().__init__(cfg)
        self.api_url = "http://127.0.0.1:8080/api/v1/retrieval"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ragflow-kzYzY5MjMwOWQwODExZjA5YWE0MDI0Mm'
        }

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Call the retrieval API and return formatted results"""
        try:
            # 处理参数类型
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    return "[Retrieval] Error: Invalid JSON format in parameters"
            elif not isinstance(params, dict):
                return "[Retrieval] Error: Parameters must be a string (JSON) or dictionary"
            
            question = params.get("question", "")
            if not question:
                return "[Retrieval] Error: Question parameter is required"

            # 确保question是字符串类型
            if not isinstance(question, str):
                question = str(question)

            # Prepare request data with defaults
            request_data = {
                "question": question,
                "dataset_ids": params.get("dataset_ids", ["1c9c4d369ce411f093700242ac170006"]),
                "document_ids": params.get("document_ids", []),  # 修复：默认为空数组
                "similarity_threshold": params.get("similarity_threshold", 0.6),
                "vector_similarity_weight": params.get("vector_similarity_weight", 0.7),
                "top_k": params.get("top_k", 4),
                "keyword": params.get("keyword", True),
                "cross_languages": params.get("cross_languages", ["ch", "en"])  # 添加跨语言支持
            }

            # Debug输出
            print(f"[DEBUG] Retrieval tool called with question: {question}")
            print(f"[DEBUG] Request data: {request_data}")

            # Make API request
            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=request_data,
                    timeout=30
                )
                response.raise_for_status()
                
                result = response.json()
                print(f"[DEBUG] API response: {result}")
                
                if result.get("code") != 0:
                    return f"[Retrieval] API Error: {result.get('message', 'Unknown error')}"

                # Format the response
                return self._format_retrieval_results(result.get("data", {}), question)

            except requests.exceptions.RequestException as e:
                return f"[Retrieval] Network Error: {str(e)}"

        except Exception as e:
            print(f"[DEBUG] Retrieval tool error: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"[Retrieval] Unexpected Error: {str(e)}"

    def _format_retrieval_results(self, data: Dict, question: str) -> str:
        """Format retrieval results into readable text"""
        chunks = data.get("chunks", [])
        doc_aggs = data.get("doc_aggs", [])
        total = data.get("total", 0)

        if total == 0:
            return f"[Retrieval] No relevant documents found for question: '{question}'"

        # Create document mapping for reference
        doc_map = {doc["doc_id"]: doc["doc_name"] for doc in doc_aggs}

        formatted_result = f"Retrieval Results for '{question}' (Found {total} relevant chunks):\n\n"
        
        for i, chunk in enumerate(chunks, 1):
            similarity = chunk.get("similarity", 0)
            content = chunk.get("content", "")
            doc_id = chunk.get("document_id", "")
            doc_name = doc_map.get(doc_id, "Unknown Document")
            
            formatted_result += f"[{i}] Document: {doc_name}\n"
            formatted_result += f"Similarity: {similarity:.3f}\n"
            formatted_result += f"Content: {content}\n"
            
            # Add highlight if available
            highlight = chunk.get("highlight", "")
            if highlight and highlight != content:
                formatted_result += f"Highlight: {highlight}\n"
            
            formatted_result += "\n---\n\n"

        return formatted_result.strip()
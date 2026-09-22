from typing import TypedDict
import copy

class ImportGraphState(TypedDict):
    """知识库导入 Graph 的状态定义，在各节点间传递共享。"""

    local_file_path:str        # 待导入的原始文件路径
    task_id:str                # 导入任务 ID
    is_md_read_enabled:bool    # 是否启用 Markdown 解析
    is_pdf_read_enabled:bool   # 是否启用 PDF 解析
    md_path:str                # 解析生成的 Markdown 文件路径
    pdf_path:str               # 解析生成的 PDF 文件路径
    file_title:str             # 文件标题
    local_dir:str              # 本地工作目录
    md_content:str             # Markdown 文本内容
    chunks:list                # 文本分块结果
    item_name:str              # 知识条目名称
    embeddings_content:list    # 向量化内容（用于写入向量库）

# 导入状态的默认初始值，所有字段均为空值
graph_default_state:ImportGraphState = {
    "task_id": "",
    "is_pdf_read_enabled": False,
    "is_md_read_enabled": False,
    "local_dir": "",
    "local_file_path": "",
    "pdf_path": "",
    "md_path": "",
    "file_title": "",
    "md_content": "",
    "chunks": [],
    "item_name": "",
    "embeddings_content": [],
}

def create_default_state(**overrides) -> ImportGraphState:
    """创建默认状态的深拷贝副本，并用 overrides 覆盖指定字段。"""
    state = copy.deepcopy(graph_default_state)  # 深拷贝，避免污染全局默认值
    state.update(overrides)
    return state

def get_default_state()->ImportGraphState:
    """获取默认状态的独立副本（深拷贝，调用方修改不影响全局默认值）。"""
    return copy.deepcopy(graph_default_state)

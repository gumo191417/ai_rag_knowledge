from pathlib import Path

from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger


def resolve_input_file(state: ImportGraphState) -> ImportGraphState:
    """
    入口识别服务（供 node_entry 调用）：解析输入文件路径，回写流程路由信息。

    1. 校验 local_file_path（为空则原样返回，流程终止）
    2. 按扩展名识别文件类型（PDF / Markdown），点亮对应解析开关
    3. 回写 is_md_read_enabled / is_pdf_read_enabled 及对应文件路径
    4. 以文件名（去扩展名）作为 file_title
    """
    # 路径为空: 不做任何处理，两个开关都不会点亮，图路由到 node_entry 后直达 END
    local_file_path = state.get("local_file_path")
    if not local_file_path:
        logger.warning("节点:node_entry, 文件路径为空，直接终止当前导入流程")
        return state

    # 按扩展名识别文件类型，开启对应解析分支
    if local_file_path.lower().endswith(".md"):
        # Markdown: 无需转换，直接作为 md_path 进入 MD 处理链路
        state["md_path"] = local_file_path
        state["is_md_read_enabled"] = True
    elif local_file_path.lower().endswith(".pdf"):
        # PDF: 点亮 PDF 分支，需先转换为 Markdown
        state["pdf_path"] = local_file_path
        state["is_pdf_read_enabled"] = True
    else:
        # 不支持的类型: 不点亮任何开关，等同终止流程
        logger.warning(
            f"节点:resolve_input_file, 不支持的文件类型: {local_file_path}，终止流程"
        )
        return state

    # 取文件名（不含扩展名）作为文件标题，如 /a/b/产品手册.pdf -> "产品手册"
    file_title = Path(local_file_path).stem
    state["file_title"] = file_title

    return state

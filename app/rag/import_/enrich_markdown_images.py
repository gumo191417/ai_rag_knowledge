import base64
import re
from mimetypes import guess_type
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from minio.deleteobjects import DeleteObject

from app.infra.llm.provider import llm_provider
from app.infra.object_storage.minio_gateway import minio_gateway
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import SUPPORTED_IMAGE_EXTENSIONS, IMAGE_CONTEXT_CHAR_LENGTH
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import logger, step_log


"""
    Markdown 图片增强服务：
        1. 扫描 Markdown 中的图片
        2. 调用多模态模型生成图片说明
        3. 上传图片到 MinIO
        4. 替换 Markdown 图片地址并回写 md_content
    具体实现步骤：
        1.获取state参数并校验 
        2.提取图片和上下文
        3.使用大模型对图片进行意图识别
        4.将图片上传到minio，并获取地址
        5.md文档内容进行替换
        6.将更新后的md文档保存到本地磁盘
        7.更新state
    数据流：
        1.state.md_path -> md_path_obj,md_content,image_path_obj
        2.md_content,image_path_obj ->
        image_info_list(
            image_name,
            image_file_obj,
            (
                pre_context,
                post_context
            )
        )
        3.

"""

def enrich_markdown_images(state: ImportGraphState) -> ImportGraphState:

    # 1. 获取参数并且校验
    md_content,md_path_obj,images_path_obj = validates_and_get_data(state)
    # 2. 提取图片和图片上下文
    image_info_list = scan_images_and_context(md_content,images_path_obj)
    # 3. 使用vlm模型对图片进行意图识别
    image_summary:dict[str,str] = summary_image_info(image_info_list,md_path_obj.stem)
    # 4. 将图片上次到minion服务器，获取图片地址
    image_url:dict[str,str] = upload_images_to_minio(image_info_list,md_path_obj.stem)
    # 5. 对md文档内容进行替换
    new_md_content = replace_old_md_content(md_content,image_summary,image_url)
    # 6. 将更新后的md文档保存到stem文件夹下
    new_md_path:str = backen_md_return_path(new_md_content,md_path_obj)
    # 7. 更新state
    state["md_content"] = new_md_content
    state["md_path"] = new_md_path
    return state

def validates_and_get_data(state:ImportGraphState) ->tuple[str,Path,Path]:
    """
    获取参数并且校验
    :param state:节点状态图
    :return:str:md文档内容，Path:md_path_obj,Path:image_path_obj
    """
    md_path = state.get("md_path")
    if not md_path:
        logger.error("md文档地址为空，Markdown 图片增强服务中止")
        raise ValueError("md文档地址为空，Markdown 图片增强服务中止")
    md_path_obj = Path(md_path)
    if not md_path_obj.is_file():
        logger.error(f"md地址为：{md_path},但md文件不存在，Markdown 图片增强服务中止")
        raise FileNotFoundError(f"md地址为：{md_path},但md文件不存在，Markdown 图片增强服务中止")

    md_path = md_path_obj.read_text(encoding="utf-8")
    image_path_obj = md_path_obj.parent / "images"
    return md_path,md_path_obj,image_path_obj

@step_log("scan_images_and_context")
def scan_images_and_context(md_content:str,image_path_obj:Path)->list[tuple[str,Path,tuple[str,str]]]:
    """
    提取图片和图片上下文
    :param md_content: md文档内容
    :param image_path_obj: 图片文件夹的Path对象
    :return: 返回元组列表，列表元素：(图片名，图片path对象，上下文元组)
    """

    if not image_path_obj.is_dir():
        logger.error(f"图像文件夹地址为：{str(image_path_obj)}，但文件夹不存在，Markdown 图片增强服务中止")
        raise FileNotFoundError(f"图像文件夹地址为：{str(image_path_obj)}，但文件夹不存在，Markdown 图片增强服务中止")

    generator = image_path_obj.iterdir()
    image_info_list: list[tuple[str,Path,tuple[str,str]]] = []
    for image_file_obj in generator:
        if image_file_obj.suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            logger.debug(f"{image_file_obj.name}不是图片,跳过,进行下一张处理!")
            continue
        image_name:str = image_file_obj.name
        match = re.search("\!\[.*?\]\(.*?" + re.escape(image_name) + ".*?\)",md_content)
        if not match:
            logger.debug(f"{image_name}没有在md_content被使用,跳过,进行下一张处理!")
            continue
        start = match.start()
        end = match.end()
        pre_context = md_content[max(start - IMAGE_CONTEXT_CHAR_LENGTH,0):start]
        post_context = md_content[end + 1 : min(end + IMAGE_CONTEXT_CHAR_LENGTH , len(md_content))]
        image_info_list.append(
            (
                image_name,
                image_file_obj,
                (
                    pre_context,
                    post_context
                )
            )
        )
        logger.info(f"已经完成了{len(image_info_list)}张图片内容的匹配!")
    return image_info_list

@step_log("summary_image_info")
def summary_image_info(image_info_list:list[tuple[str,Path,tuple[str,str]]],root_folder:str)->dict[str,str]:
    """

    :param image_info_list: 文档图片信息列表
    :param root_folfer:
    :return:
    """
    images_summary :dict[str,str] = {}
    vision_model = llm_provider.vision_chat()
    for image_name,image_file_obj , image_context in image_info_list:
        image_des = load_prompt("image_summary",root_folder=root_folder,image_content=image_context)
        image_type:str = guess_type(image_name)[0]
        image_base64:str = base64.b64encode(image_file_obj.read_bytes()).decode("utf-8")
        message = HumanMessage(
            content=[
                {
                    "type":"text",
                    "text":image_des
                },
                {
                    "type":"image_url",
                    "image_url":{"url":f"data:{image_type};base64,{image_base64}"}
                }
            ]
        )
        chains =vision_model |StrOutputParser()
        summary= chains.invoke([message])
        images_summary[image_name] = summary
    logger.info(f"已经完成{root_folder}文件夹中的所有图片内容总结,总结图的内容对数为:{len(images_summary)}")
    return images_summary

@step_log("upload_images_to_minio")
def upload_images_to_minio(image:list[tuple[str,Path,tuple[str,str]]],stem:str) -> dict[str,str]:
    minio_client = minio_gateway.client
    image_url :dict[str,str] = {}
    objects = minio_client.list_objects(
        bucket_name=minio_gateway.bucket_name,
        prefix=minio_gateway.image_dir[1:] +"/" + stem,
        recursive=True
    )
    if objects:
        delete_objects_list =[DeleteObject(obj.object_name) for obj in objects]
        errors =minio_client.remove_objects(
            bucket_name=minio_gateway.bucket_name,
            delete_object_list = delete_objects_list
        )
        for error in errors:
            logger.warning(f"删除{stem}文件夹下的文件出现问题：{error}")

    # 循环处理每一张图片,上次到minio服务器
    for image_name,image_path_obj,_ in image:
        try:
            minio_client.fput_object(
                bucket_name=minio_gateway.bucket_name,
                object_name =minio_gateway.image_dir[1:] + "/" + stem + "/" + image_name,
                file_path=str(image_path_obj),
                content_type = guess_type(image_name)[0]
            )
            url:str =minio_gateway.build_image_url(stem,image_name)
            image_url[image_name] = url
        except Exception as e:
            logger.exception(f"{image_name}图书上传失败,跳过本次,进行下一张图片处理!")
            continue

    return image_url



@step_log("replace_old_md_content")
def replace_old_md_content(md_content:str,image_summary:dict[str,str],image_url:dict[str,str]) -> str:
    for image_name,url in image_url.items():
        summary = image_summary[image_name]
        re_component =re.compile(r"\!\[.*?\]\(.*?" +re.escape(image_name) +  ".*?\)")
        md_content:str = re_component.sub(lambda _:f"![{summary}]({url})",md_content)
    logger.info("已经完成md_content内部图片标签的替换,获得新的md_content内容")
    return md_content


@step_log("backup_md_return_path")
def backen_md_return_path(md_content:str,md_path_obj:Path):
    new_md_path_obj =md_path_obj.with_name(f"{md_path_obj.stem}_new.md")
    new_md_path_obj.write_text(data=md_content,encoding="utf-8")
    logger.info(f"已经完成md录入磁盘，最新md文档地址：{str(new_md_path_obj)}")
    return str(new_md_path_obj)
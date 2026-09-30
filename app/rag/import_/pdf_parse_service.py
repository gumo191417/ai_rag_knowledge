import shutil
import time
from pathlib import Path
import requests

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import MINERU_DOWNLOAD_TIMEOUT_SECONDS, MINERU_POLL_TIMEOUT_SECONDS, \
    MINERU_POLL_INTERVAL_SECONDS
from app.shared.runtime.logger import logger,PROJECT_ROOT
from app.infra.config.providers import infra_config


def parse_pdf_to_markdown(state: ImportGraphState) -> ImportGraphState:
    """
    PDF 解析服务：
        将本地pdf文件,利用minerU,解析成md文件!
        最终存储到项目下 /output/文件名命名的文件夹 / 原文件名.md | images/图片
        修改state -> md_path => md地址

    节点参数:
     传入:  pdf_path / local_dir / task_id
     生成:  md_path

     1.核心参数校验
     2.minerU处理流程 [申请上传文件地址]
     3.minerU处理流程 [上传文件]
     4.minerU处理流程 [轮询获取解析结果->zip_url]
     5.文件的下载和解压
     6.修改state -> md_path赋值
    """
    # 1 df校验 pdf_path 与 local_file_path
    pdf_path_obj, local_file_path_obj = validates_pdf_paths(state)

    # 2 申请上传文件地址
    batch_id,upload_url =apply_mineru_get_upload_url(pdf_path_obj.name)

    # 3 上传PDF文件到MinerU的存储地址
    upload_file_to_url(upload_url, pdf_path_obj)

    # 4. 轮询获取解析结果
    full_zip_file_url = poll_mineru_zip_url(batch_id)

    # 5. 下载并解压重命名文件
    md_path: str = download_and_extract_md(full_zip_file_url, local_file_path_obj, pdf_path_obj.stem)

    state["md_path"] = md_path
    return state

# 核心参数校验
def validates_pdf_paths(state:ImportGraphState)-> tuple[Path,Path]:
    # 1 获取pdf_path,local_dir
    pdf_path = state.get("pdf_path")
    local_dir = state.get("local_dir")
    # 2 非空检验
    if not pdf_path:
        logger.error("pdf_path为空值，节点中断，中止流程")
        raise ValueError("pdf_path为空值，节点中断，中止流程")
    if not local_dir:
        local_dir = PROJECT_ROOT / "output"
        logger.warning(f"本地文件目录地址为空，自定义地址为：{local_dir},业务继续")
        state["local_dir"] = local_dir
    # 3 转换为Path对象
    pdf_path_obj = Path(pdf_path)
    local_dir_obj:Path = Path(local_dir)
    # 4 检查pdf_path_obj 文件对象是否真实存在
    if not pdf_path_obj.is_file():
        logger.error(f"pdf_path的路径地址为：{pdf_path},但文件不存在，业务中止")
        raise FileNotFoundError(f"pdf_path的路径地址为：{pdf_path},但文件不存在，业务中止")
    # 5 检查local_dir 是否存在，不存在则创建文件夹
    if not local_dir_obj.is_dir():
        logger.warning(f"local_dir的路径是：{local_dir}，但没有文件夹。创建文件夹并继续进行业务")
        local_dir_obj.mkdir(exist_ok=True,parents=True)
    # 6 返回pdf_path_obj，local_dir_obj对象
    return pdf_path_obj,local_dir_obj

def apply_mineru_get_upload_url(pdf_file_name:str) -> tuple[str,str]:
    """
    申请上传文件地址
    :param pdf_file_name: 文件名
    :return: upload_url
    """
    # 1 组装请求头
    token = infra_config.mineru_config.api_key
    url = f"{infra_config.mineru_config.base_url}/file-urls/batch"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    # 2 组装请求体
    data = {
        "files": [
            {"name": f"{pdf_file_name}"}
        ],
        "model_version": "vlm"
    }
    # 3 向对应的接口发送post请求，并阻塞等待
    response = requests.post(
        headers=header,
        url=url,
        json=data,
        timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS
    )
    # 4 判断http协议网络状态status_code
    status_code = response.status_code
    if status_code != 200:
        logger.error(f"网络异常，状态码：{status_code},业务中断")
        raise RuntimeError(f"网络异常，状态码：{status_code},业务中断")
    # 5 判断业务状态码code
    result_json = response.json()
    code = result_json.get("code")
    if code != 0:
        logger.error(f"向minerU服务器申请解析地址,业务状态码为:{code},请求失败!业务无法继续,提前终止!!")
        raise RuntimeError(f"向minerU服务器申请解析地址,业务状态码为:{code},请求失败!业务无法继续,提前终止!!")
    # 6 获取目标结果batch_id/upload_url地址
    batch_id = result_json.get("data").get("batch_id")
    upload_url = result_json.get("data").get("file_urls")[0]
    return batch_id,upload_url

def upload_file_to_url(upload_url:str,pdf_path_obj:Path)-> None:
    """
    向指定的文件服务器的地址,上传文件,注意使用的请求方式为put
    :param upload_url: 上传文件地址
    :param pdf_path_obj: pdf文件地址对象
    :return:
    """
    # 1 获取pdf二进制数据
    pdf_binary_data = pdf_path_obj.read_bytes()
    # 2 向指定地址发起put对象，传递二进制数据
    with requests.Session() as session:
        session.trust_env = False
        response = session.put(url=upload_url,data=pdf_binary_data,timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
    # 3 判断响应状态码,不是200抛出异常!
    status = response.status_code
    if status != 200:
        logger.error(f"向:{upload_url}地址上传文件,网络状态失败:{status},业务无法继续,提前终止!!")
        raise RuntimeError(f"向:{upload_url}地址上传文件,网络状态失败:{status},业务无法继续,提前终止!!")
    return



"""
poll_mineru_zip_url(batch_id:str) -> str:
    6.1 接收常量参数 临时变量接收值 最大轮询时间 / 轮询间隔时间 / 记录起始时间
    6.2 死循环 while True:
        6.2.1 有没有超过最大等待时间 [1~N]
        6.2.2 向指定的地址请求查询解析状态
        6.2.3 判断网络状态码status_code != 200  [判断是否可以给与机会(5xx),可以等待重试 / 其他的也需要抛出异常终止轮询 ]
        6.2.4 判断业务状态码code != 0 [需要抛出异常终止轮询]
        6.2.5 判断文件的解析状态state
              done -> zip -> return 
              fail -> 失败 -> raise
              else -> 休眠 再次请求
"""
def poll_mineru_zip_url(batch_id:str)->str:
    """
    通过batch_id轮询获取解析结果, 获取的结果是一个url
    :param batch_id: 文件ID
    :return: 压缩文件下载url地址
    """
    # 1 接收常量参数：最大轮询时间/轮询间隔时间/记录起始时间
    max_timeout = MINERU_POLL_TIMEOUT_SECONDS
    interval_time = MINERU_POLL_INTERVAL_SECONDS
    start_time = time.time()
    url = f"{infra_config.mineru_config.base_url}/extract-results/batch/{batch_id}"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {infra_config.mineru_config.api_key}"
    }

    # 2 轮询接收
    while True:
        # 有没有超过最大等待时间
        if time.time() - start_time   >= max_timeout:
            logger.error(f"轮询请求超时，运行时间为：{time.time() - start_time }，业务中止")
            raise TimeoutError(f"轮询请求超时，运行时间为：{time.time() - start_time }，业务中止")
        response = requests.get(url=url,headers=header,timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
        status = response.status_code
        if status != 200:
            if 500 <= status < 600:
                logger.warning(f"轮询获取解析结果,出现服务器异常,状态码为:{status},稍后重试!!")
                time.sleep(interval_time)  # 线程休眠!
                continue
            logger.error(
                f"轮询获取解析结果,出现异常,状态码为:{status},异常是不可修复和重试,业务无法继续,提前终止!!")
            raise RuntimeError(
                f"轮询获取解析结果,出现异常,状态码为:{status},异常是不可修复和重试,业务无法继续,提前终止!!")

        json_data = response.json()
        code = json_data.get("code", -1)
        if code != 0:
            logger.error(
                f"轮询获取解析结果,业务状态出现异常,code为:{code},异常是不可修复和重试,业务无法继续,提前终止!!")
            raise RuntimeError(
                f"轮询获取解析结果,业务状态出现异常,code为:{code},异常是不可修复和重试,业务无法继续,提前终止!!")

        result = json_data.get("data",{}).get("extract_result",[])[0]
        state =result.get("state")

        if state == "done":
            full_zip_url: str = result.get("full_zip_url")
            return full_zip_url
        elif state == "failed":
            logger.error(f"文件解析失败,业务无法继续,提前终止!!")
            raise RuntimeError(f"文件解析失败,业务无法继续,提前终止!!")
        else:
            logger.info(f"文件正在解析中,当前状态为:{state},稍后重试!!")
            time.sleep(interval_time)
            continue

def download_and_extract_md(zip_file_url:str,local_dir_obj:Path,stem:str)->str:
    response = requests.get(zip_file_url,timeout=MINERU_DOWNLOAD_TIMEOUT_SECONDS)
    status_code = response.status_code
    if status_code != 200:
        logger.error(f"从:{zip_file_url}下载文件重现网络异常,状态码为:{status_code},业务无法继续,提前终止!!")
        raise RuntimeError(f"从:{zip_file_url}下载文件重现网络异常,状态码为:{status_code},业务无法继续,提前终止!!")

    zip_file_obj = local_dir_obj / f"{stem}_result.zip"
    data = response.content
    zip_file_obj.write_bytes(data)

    zip_file_dir = local_dir_obj / stem
    if zip_file_dir.is_dir():
        shutil.rmtree(zip_file_dir)
    zip_file_dir.mkdir(parents=True,exist_ok=True)
    shutil.unpack_archive(zip_file_obj,zip_file_dir)

    md_list:list[Path] =list(zip_file_dir.rglob("*.md"))

    if not md_list:
        logger.error(f"已经将文件解压到了{local_dir_obj}文件夹,但是内部没有md文件,业务无继续,提前终止!!")
        raise RuntimeError(f"已经将文件解压到了{local_dir_obj}文件夹,但是内部没有md文件,业务无继续,提前终止!!")

    for md_file in md_list:
        if md_file.stem == stem:
            logger.info(f"解压后直接存在原文件名({md_file.name})对应的md文件,无需重命名,直接返回即可!")
            return str(md_file)

    target_md_file :Path |None = None
    for md_file in md_list:
        if md_file.stem == "full":
            target_md_file = md_file
            break

    if target_md_file:
        new_target_md_obj = target_md_file.with_name(f"{stem}.md")
        new_md_obj:Path =target_md_file.rename(new_target_md_obj)
        logger.info(f"已经完成full.md重命名,新的文件地址为:{new_md_obj}~")
        return str(new_md_obj)
    else:
        # 7.11 终止业务
        logger.error(
            f"解压后的文件夹中存在{len(md_list)}个md文件,但是没有叫原文件名{stem}/full.md文件,也无法确定哪个文件,业务无法继续,提前终止!!")
        raise RuntimeError(
            f"解压后的文件夹中存在{len(md_list)}个md文件,但是没有叫原文件名{stem}/full.md文件,也无法确定哪个文件,业务无法继续,提前终止!!")










"""
提示词模板加载模块

本模块负责从本地文件系统中发现并加载 Jinja2 模板文件。
模板文件统一存放在 prompts/jinja2/ 目录下，以 .jinja2 为后缀。
加载函数通过模板名称定位对应的 jinja2 文件并读取其文本内容，
返回的字符串交由 Jinja2 引擎进行渲染（填充变量）。

文件约定:
    - 模板目录: prompts/jinja2/
    - 文件命名: {prompt_template_name}.jinja2
    - 文件编码: UTF-8
"""
from pathlib import Path


def load_prompt_template(prompt_template_nam: str) -> str:
    """
    根据模板名称加载 Jinja2 提示词模板文件的内容。

    工作原理:
        1. 定位当前文件（loader.py）所在的 prompts/ 目录
        2. 拼接子路径 jinja2/{prompt_template_nam}.jinja2
        3. 以 UTF-8 编码读取文件全部文本内容

    :param prompt_template_nam: 模板名称（不含路径和 .jinja2 后缀）
    :return: 模板文件的原始文本字符串
    """
    # 以当前源文件所在目录为基准，定位 jinja2 子目录下的模板文件
    file_path = Path(__file__).resolve().parents[0] / "jinja2" / f"{prompt_template_nam}.jinja2"

    return file_path.read_text(encoding="utf-8")

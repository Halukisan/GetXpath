from DrissionPage import ChromiumPage
import json
import re

def get_robust_xpath(element):
    """生成更健壮的XPath表达式，处理空格和动态文本"""
    # 获取基本属性
    tag = element.tag
    raw_text = element.text.strip() if element.text else ""
    
    # 清理文本：移除多余空格和不可见字符
    cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
    
    # 获取唯一标识属性
    attributes = []
    for attr in ['id', 'class', 'href', 'src', 'name', 'type', 'value']:
        attr_val = element.attr(attr)
        if attr_val:
            # 简化class值（通常有多个类名）
            if attr == 'class':
                # 取第一个有意义的class
                first_class = attr_val.split()[0] if attr_val else ""
                if first_class and len(first_class) > 2:  # 忽略太短的class
                    attributes.append(f"contains(@class, '{first_class}')")
            else:
                # 截取部分属性值避免过长
                attr_val_short = attr_val[:30] + '...' if len(attr_val) > 30 else attr_val
                attributes.append(f"contains(@{attr}, '{attr_val_short}')")
    
    # 构建XPath选项
    options = []
    
    # 选项1：使用清理后的文本 + contains()
    if cleaned_text:
        # 取文本的前5个和后5个字符（避免中间变化）
        text_part = cleaned_text
        if len(cleaned_text) > 10:
            text_part = f"{cleaned_text[:5]}...{cleaned_text[-5:]}"
        options.append(f"contains(text(), '{text_part}')")

    
    # 组合最终表达式
    if options:
        conditions = ' or '.join([f"({opt})" for opt in options])
        return f"//{tag}[{conditions}]"
    else:
        # 最后手段：仅使用标签
        return f"//{tag}"

# 初始化浏览器
page = ChromiumPage()

# 访问目标网址
page.get('https://www.nmg.gov.cn/zwgk/zfxxgk/zfxxgkml/?gk=3&cid=3696#iframe')

# 存储点击标签的XPath信息
xpathList4Click = []

try:
    # 点击第一个标签：政 策
    policy_tab = page.ele('@text():政策', timeout=15)
    if policy_tab:
        policy_xpath = get_robust_xpath(policy_tab)
        xpathList4Click.append(policy_xpath)
        
        policy_tab.click()
        print(f"已点击: 政策 - XPath: {policy_xpath}")
        page.wait.load_start()
        page.wait(3)  # 额外等待确保加载
    else:
        print("未找到 '政策' 标签")

    # 点击第二个标签：其他文件
    other_file_tab = page.ele('@text():其他文件', timeout=15)
    if other_file_tab:
        other_xpath = get_robust_xpath(other_file_tab)
        xpathList4Click.append(other_xpath)
        
        other_file_tab.click()
        print(f"已点击: 其他文件 - XPath: {other_xpath}")
        page.wait.load_start()
        page.wait(3)  # 额外等待确保加载
    else:
        print("未找到 '其他文件' 标签")

    # 获取渲染后的HTML
    rendered_html = page.html
    
    # 保存HTML到文件
    with open('rendered_page.html', 'w', encoding='utf-8') as f:
        f.write(rendered_html)
    print("HTML已保存到 rendered_page.html")
    
    # 返回结果
    result = {
        "html": rendered_html,
        "xpathList4Click": xpathList4Click
    }
    
    # 打印结果
    print("\n最终结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"操作出错: {str(e)}")
    # 出错时保存当前HTML
    try:
        rendered_html = page.html
        with open('error_page.html', 'w', encoding='utf-8') as f:
            f.write(rendered_html)
        print("已保存出错时的HTML到 error_page.html")
    except:
        pass

finally:
    # 关闭浏览器
    page.quit()
    print("浏览器已关闭")
import re
import requests
import time
import yaml
from lxml import html
from yaml import SafeLoader
from urllib.parse import urlparse

def get_html_content(url):
    """获取网页HTML内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None

def find_list_container(page_tree):
    """使用分层搜索策略查找最优列表容器"""
    list_selectors = [
        "//li",
        "//tr",
        "//article",
        "//div[contains(@class, 'item')]",
        "//div[contains(@class, 'list')]",
        "//ul//li",
        "//ol//li",
        "//table//tr"
    ]
    
    def count_list_items(element):
        """统计元素内的列表项数量"""
        items = element.xpath(
            ".//li | .//tr | .//article | "
            ".//div[contains(@class, 'item')]"
        )
        return len(items)
    
    def get_direct_parent(elements):
        """获取元素集合的直接父元素们"""
        parents = set()
        for element in elements:
            parent = element.getparent()
            if parent is not None:
                parents.add(parent)
        return list(parents)
    
    # 第一层：找到所有可能的列表项
    all_items = []
    for selector in list_selectors:
        items = page_tree.xpath(selector)
        all_items.extend(items)
    
    if not all_items:
        return None
    
    # 按照父元素分组，找到包含最多列表项的父元素
    parent_counts = {}
    for item in all_items:
        parent = item.getparent()
        if parent is not None:
            if parent not in parent_counts:
                parent_counts[parent] = 0
            parent_counts[parent] += 1
    
    if not parent_counts:
        return None
    
    # 获取包含最多列表项的父元素
    current_container = max(parent_counts.items(), key=lambda x: x[1])[0]
    max_items = parent_counts[current_container]
    
    # 逐层向上搜索，直到找到最优容器
    while True:
        # 获取当前容器的父元素
        parent = current_container.getparent()
        if parent is None or parent.tag == 'html':
            break
            
        # 计算父元素中的列表项数量
        parent_items = count_list_items(parent)
        
        # 如果父元素的列表项数量显著增加，说明范围太大，保持当前容器
        if parent_items > max_items * 1.5:
            break
            
        # 获取同级元素中的列表项数量
        siblings = parent.xpath(".//*[self::li or self::tr or self::article or self::div[contains(@class, 'item')]]")
        if len(siblings) < 3:
            break
            
        # 更新当前容器和最大列表项数量
        current_container = parent
        max_items = parent_items
        
        # 如果当前容器只包含很少的直接子列表项，说明已经到达最优层级
        direct_items = len(current_container.xpath(
            "./li | ./tr | ./article | ./div[contains(@class, 'item')]"
        ))
        if direct_items < 3:
            break
    
    return current_container
def generate_xpath(element):
    """从元素生成XPath表达式"""
    if not element:
        return None

    tag = element.tag

    # 1. 优先使用ID（如果存在）
    if element.get('id'):
        return f"//{tag}[@id='{element.get('id')}']"

    # 2. 使用最长类名（如果存在）
    classes = element.get('class')
    if classes:
        class_list = [cls.strip() for cls in classes.split() if cls.strip()]
        if class_list:
            # 选择最长的类名
            longest_class = max(class_list, key=len)
            return f"//{tag}[contains(concat(' ', normalize-space(@class), ' '), ' {longest_class} ')]"

    # 3. 使用其他属性（如 aria-label 等）
    for attr in ['aria-label', 'role', 'data-testid', 'data-role']:
        attr_value = element.get(attr)
        if attr_value:
            return f"//{tag}[@{attr}='{attr_value}']"

    # 4. 尝试找到最近的有标识符的祖先，生成相对路径
    def find_closest_identifier(el):
        parent = el.getparent()
        while parent is not None and parent.tag != 'html':
            # 优先使用 ID
            if parent.get('id'):
                return parent
            # 使用类名
            parent_classes = parent.get('class')
            if parent_classes:
                parent_class_list = [cls.strip() for cls in parent_classes.split() if cls.strip()]
                if parent_class_list:
                    return parent
            parent = parent.getparent()
        return None

    ancestor = find_closest_identifier(element)
    if ancestor is not None:
        # 生成祖先的 XPath
        ancestor_xpath = generate_xpath(ancestor)
        # 生成从祖先到当前元素的相对路径
        def generate_relative_path(ancestor_el, target_el):
            path = []
            current = target_el
            while current is not None and current != ancestor_el:
                index = 1
                sibling = current.getprevious()
                while sibling is not None:
                    if sibling.tag == current.tag:
                        index += 1
                    sibling = sibling.getprevious()
                path.insert(0, f"{current.tag}[{index}]")
                current = current.getparent()
            return '/' + '/'.join(path)

        relative_path = generate_relative_path(ancestor, element)
        return f"{ancestor_xpath}{relative_path}"

    # 5. 基于位置的 XPath（最后手段）
    path = []
    current = element
    while current is not None and current.tag != 'html':
        index = 1
        sibling = current.getprevious()
        while sibling is not None:
            if sibling.tag == current.tag:
                index += 1
            sibling = sibling.getprevious()
        path.insert(0, f"{current.tag}[{index}]")
        current = current.getparent()

    return '/' + '/'.join(path)

def validate_xpath(xpath, html_content):
    """验证XPath是否返回有效结果"""
    try:
        tree = html.fromstring(html_content)
        results = tree.xpath(xpath)
        
        if not results:
            return False, "未找到元素"
        
        container = results[0]
        list_items = container.xpath(".//li | .//tr | .//article | .//div[contains(concat(' ', normalize-space(@class), ' '), ' item ')]")

        
        if len(list_items) >= 3:
            return True, f"找到 {len(list_items)} 个列表项"
        
        return False, f"仅找到 {len(list_items)} 个列表项（需要至少3个）"
    except Exception as e:
        return False, f"XPath执行错误: {str(e)}"

def process_entry(entry, max_retries=3):
    """处理单个条目"""
    url = entry['url']
    print(f"\n处理: {entry['name']}")
    print(f"URL: {url}")
    
    html_content = get_html_content(url)
    if not html_content:
        print("获取HTML内容失败")
        return {**entry, 'xpath': None, 'status': 'fetch_failed'}
    
    best_xpath = None
    validation_result = ""
    candidate_xpath = None  # 添加初始化

    for attempt in range(1, max_retries + 1):
        print(f"\n尝试 #{attempt}")
        
        tree = html.fromstring(html_content)
        
        container = find_list_container(tree)
        
        if not container:
            print("未找到有效的列表容器")
            continue
        
        candidate_xpath = generate_xpath(container)
        if not candidate_xpath:
            print("无法生成XPath")
            time.sleep(1)
            continue

        print(f"XPath: {candidate_xpath}")
        is_valid, validation_msg = validate_xpath(candidate_xpath, html_content)
        print(f"XPath候选: {candidate_xpath}")
        print(f"验证结果: {validation_msg}")
        
        if is_valid:
            best_xpath = candidate_xpath
            validation_result = validation_msg
            break
        elif attempt == max_retries:
            # 最后一次尝试，使用最佳候选（即使不完美）
            best_xpath = candidate_xpath
            validation_result = f"最终选择: {validation_msg}"

    if best_xpath:
        print(f"✓ 最终XPath: {best_xpath}")
        return {**entry, 'xpath': best_xpath, 'status': 'success'}
    
    print("✗ 未能找到有效XPath")
    return {**entry, 'xpath': None, 'status': 'failed'}

def parse_input_file(input_file):
    """解析输入文件"""
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则表达式匹配每个条目
    pattern = r'name:\s*(.*?)\s*url:\s*(https?://\S+)\s*'
    matches = re.findall(pattern, content)
    
    entries = []
    for match in matches:
        entries.append({
            'name': match[0],
            'url': match[1]
        })
    
    return entries

def write_output_file(results, output_file):
    """写入输出文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            # 只保留原始字段和xpath
            output_data = {
                'name': result['name'],
                'url': result['url'],
                'xpath': result.get('xpath', '')  # 如果没有xpath则为空字符串
            }
            
            # 写入条目
            f.write(f"name: {output_data['name']}\n")
            f.write(f"url: {output_data['url']}\n")
            f.write(f"xpath: \"{output_data['xpath']}\"\n")
            f.write("---\n")  # 添加分隔符

def process_yml_file(input_file, output_file):
    """处理YML文件"""
    # 解析输入文件
    entries = parse_input_file(input_file)
    total = len(entries)
    
    if total == 0:
        print("未找到有效条目")
        return
    
    print(f"找到 {total} 个待处理条目")
    
    # 处理条目
    results = []
    for i, entry in enumerate(entries):
        print(f"\n{'='*40}")
        print(f"处理条目 {i+1}/{total}")
        result = process_entry(entry)
        results.append(result)
        print(f"{'='*40}")
    
    # 写入结果
    write_output_file(results, output_file)
    
    # 生成统计报告
    success_count = sum(1 for r in results if r.get('status') == 'success')
    failure_count = total - success_count
    
    print(f"\n处理完成: {success_count} 成功, {failure_count} 失败")
    print(f"结果已保存至: {output_file}")

if __name__ == "__main__":
    input_file = "test2.yml"    # 输入文件路径
    output_file = "CL3output.yml"  # 输出文件路径
    
    process_yml_file(input_file, output_file)
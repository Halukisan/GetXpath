import re
import requests
import time
from lxml import html

def get_html_content(url):
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
        return None

def find_list_container(page_tree):
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
        items = element.xpath(
            ".//li | .//tr | .//article | "
            ".//div[contains(@class, 'item')]"
        )
        return len(items)
    
    all_items = []
    for selector in list_selectors:
        items = page_tree.xpath(selector)
        all_items.extend(items)
    
    if not all_items:
        return None
    
    
    parent_counts = {}
    for item in all_items:
        parent = item.getparent()
        if parent is not None:
            if parent not in parent_counts:
                parent_counts[parent] = 0
            parent_counts[parent] += 1
    
    if not parent_counts:
        return None
    
    current_container = max(parent_counts.items(), key=lambda x: x[1])[0]
    max_items = parent_counts[current_container]
    
    while True:
        parent = current_container.getparent()
        if parent is None or parent.tag == 'html':
            break
            
        parent_items = count_list_items(parent)
        
        if parent_items > max_items * 1.5:
            break
            
        siblings = parent.xpath(".//*[self::li or self::tr or self::article or self::div[contains(@class, 'item')]]")
        if len(siblings) < 3:
            break
            
        current_container = parent
        max_items = parent_items
        
        direct_items = len(current_container.xpath(
            "./li | ./tr | ./article | ./div[contains(@class, 'item')]"
        ))
        if direct_items < 3:
            break
    
    return current_container
def generate_xpath(element):
    if not element:
        return None

    tag = element.tag

    if element.get('id'):
        return f"//{tag}[@id='{element.get('id')}']"

    classes = element.get('class')
    if classes:
        class_list = [cls.strip() for cls in classes.split() if cls.strip()]
        if class_list:
            longest_class = max(class_list, key=len)
            return f"//{tag}[contains(concat(' ', normalize-space(@class), ' '), ' {longest_class} ')]"

    for attr in ['aria-label', 'role', 'data-testid', 'data-role']:
        attr_value = element.get(attr)
        if attr_value:
            return f"//{tag}[@{attr}='{attr_value}']"

    def find_closest_identifier(el):
        parent = el.getparent()
        while parent is not None and parent.tag != 'html':
            if parent.get('id'):
                return parent
            parent_classes = parent.get('class')
            if parent_classes:
                parent_class_list = [cls.strip() for cls in parent_classes.split() if cls.strip()]
                if parent_class_list:
                    return parent
            parent = parent.getparent()
        return None

    ancestor = find_closest_identifier(element)
    if ancestor is not None:
        ancestor_xpath = generate_xpath(ancestor)
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
    url = entry['url']
    
    html_content = get_html_content(url)
    if not html_content:
        return {**entry, 'xpath': None, 'status': 'fetch_failed'}
    
    best_xpath = None
    validation_result = ""
    candidate_xpath = None   

    for attempt in range(1, max_retries + 1):
        print(f"\n尝试 #{attempt}")
        
        tree = html.fromstring(html_content)
        
        container = find_list_container(tree)
        
        if not container:
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
             
            best_xpath = candidate_xpath
            validation_result = f"最终选择: {validation_msg}"

    if best_xpath:
        print(f"✓ 最终XPath: {best_xpath}")
        return {**entry, 'xpath': best_xpath, 'status': 'success'}
    
    print("✗ 未能找到有效XPath")
    return {**entry, 'xpath': None, 'status': 'failed'}

def parse_input_file(input_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
     
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
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
             
            output_data = {
                'name': result['name'],
                'url': result['url'],
                'xpath': result.get('xpath', '')   
            }
            
             
            f.write(f"name: {output_data['name']}\n")
            f.write(f"url: {output_data['url']}\n")
            f.write(f"xpath: \"{output_data['xpath']}\"\n")
            f.write("---\n")   

def process_yml_file(input_file, output_file):
     
    entries = parse_input_file(input_file)
    total = len(entries)
    
    if total == 0:
        print("未找到有效条目")
        return
    
    print(f"找到 {total} 个待处理条目")
    
     
    results = []
    for i, entry in enumerate(entries):
        print(f"\n{'='*40}")
        print(f"处理条目 {i+1}/{total}")
        result = process_entry(entry)
        results.append(result)
        print(f"{'='*40}")
    
     
    write_output_file(results, output_file)
    
     
    success_count = sum(1 for r in results if r.get('status') == 'success')
    failure_count = total - success_count
    
    print(f"\n处理完成: {success_count} 成功, {failure_count} 失败")
    print(f"结果已保存至: {output_file}")

if __name__ == "__main__":
    input_file = "test2.yml"     
    output_file = "CL3output.yml"   
    
    process_yml_file(input_file, output_file)
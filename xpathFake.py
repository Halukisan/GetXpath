import re
import requests
import time
from queue import Queue
from threading import Lock
from lxml import html
from yaml import SafeLoader
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor
from webdriver_pool import WebDriverPool

# 创建全局的WebDriver池
driver_pool = WebDriverPool(pool_size=1)  # 根据机器性能调整池大小

def get_html_content(url):
    """获取网页HTML内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None

def get_html_content_Selenium(url, max_retries=4):
    """使用 Selenium 获取页面内容"""
    for attempt in range(max_retries):
        driver = None
        try:
            driver = driver_pool.get_driver()
            driver.set_page_load_timeout(180)
            driver.set_script_timeout(180)
            
            driver.get(url)
            time.sleep(15)
            
            html_content = driver.page_source
            driver_pool.return_driver(driver)
            return html_content
            
        except Exception as e:
            print(f"获取页面失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if driver:
                driver_pool.return_driver(driver)
            
            if attempt == max_retries - 1:
                print("所有重试都失败，尝试使用备用方法")
                return get_html_content(url)
                
            time.sleep(5)
    
    return None
def remove_header_footer_by_content_traceback(body):
    
    # 首部内容特征关键词
    header_content_keywords = [
        '登录', '注册', '首页', '主页', '无障碍', '政务', '办事', '互动', 
        '走进', '移动版', '手机版', '导航', '菜单', '搜索', '市政府',
        'login', 'register', 'home', 'menu', 'search', 'nav'
    ]
    
    # 尾部内容特征关键词
    footer_content_keywords = [
        '网站说明', '网站标识码', '版权所有', '主办单位', '承办单位', 
        '技术支持', '联系我们', '网站地图', '隐私政策', '免责声明',
        '备案号', 'icp', '公安备案', '政府网站', '网站管理',
        'copyright', 'all rights reserved', 'powered by', 'designed by'
    ]
    
    # 查找包含首部特征文字的元素
    header_elements = []
    for keyword in header_content_keywords:
        xpath = f"//*[contains(text(), '{keyword}')]"
        elements = body.xpath(xpath)
        header_elements.extend(elements)
    
    # 查找包含尾部特征文字的元素
    footer_elements = []
    for keyword in footer_content_keywords:
        xpath = f"//*[contains(text(), '{keyword}')]"
        elements = body.xpath(xpath)
        footer_elements.extend(elements)
    
    # 收集需要删除的容器
    containers_to_remove = set()
    
    # 处理首部元素
    for element in header_elements:
        container = find_header_footer_container(element)
        if container and container not in containers_to_remove:
            containers_to_remove.add(container)
            print(f"发现首部容器: {container.tag} class='{container.get('class', '')[:50]}'")
    
    # 处理尾部元素
    for element in footer_elements:
        container = find_footer_container_by_traceback(element)
        if container and container not in containers_to_remove:
            containers_to_remove.add(container)
            print(f"发现尾部容器: {container.tag} class='{container.get('class', '')[:50]}'")
    
    # 额外检查：查找所有直接包含header/footer标签的div容器
    header_divs = body.xpath(".//div[.//header] | .//div[.//footer] | .//div[.//nav]")
    for div in header_divs:
        # 检查这个div是否包含首部/尾部内容特征
        div_text = div.text_content().lower()
        
        header_count = sum(1 for keyword in header_content_keywords if keyword in div_text)
        footer_count = sum(1 for keyword in footer_content_keywords if keyword in div_text)
        
        if header_count >= 2 or footer_count >= 2:
            if div not in containers_to_remove:
                containers_to_remove.add(div)    
    # 删除容器
    removed_count = 0
    for container in containers_to_remove:
        try:
            parent = container.getparent()
            if parent is not None:
                parent.remove(container)
                removed_count += 1
        except Exception as e:
            print(f"删除容器时出错: {e}")
    
    return body

def find_header_footer_container(element):
    """通过回溯找到包含首部/尾部特征的容器 - 增强版"""
    current = element
    
    # 向上回溯查找容器
    while current is not None and current.tag != 'html':
        # 检查当前元素是否为容器（div、section、header、footer、nav等）
        if current.tag in ['div', 'section', 'header', 'footer', 'nav', 'aside']:
            # 检查容器是否包含首部/尾部结构特征
            classes = current.get('class', '').lower()
            elem_id = current.get('id', '').lower()
            tag_name = current.tag.lower()
            
            # 首部结构特征
            header_indicators = ['header', 'nav', 'navigation', 'menu', 'topbar', 'banner', 'menubar', 'head']
            # 尾部结构特征
            footer_indicators = ['footer', 'foot', 'bottom', 'end', 'copyright', 'links', 'sitemap', 'contact']
            
            # 检查是否包含首部或尾部结构特征
            for indicator in header_indicators + footer_indicators:
                if (indicator in classes or indicator in elem_id or indicator in tag_name):
                    return current
        
        # 检查是否到达顶层标签
        parent = current.getparent()
        if parent is None or parent.tag in ['html', 'head', 'body', 'script', 'meta']:
            # 如果父级是html或body，说明已经到顶了
            break
        
        # 继续向上查找
        current = parent
    
    # 特殊处理：如果当前元素被div包装，但div本身没有明显特征
    # 检查当前元素的父级是否是div，且祖父级是body/html
    if (element.getparent() and 
        element.getparent().tag == 'div' and 
        element.getparent().getparent() and 
        element.getparent().getparent().tag in ['body', 'html']):
        
        # 检查这个div是否包含首部/尾部内容特征
        div_element = element.getparent()
        div_text = div_element.text_content().lower()
        
        # 首部内容特征关键词
        header_content_keywords = [
            '登录', '注册', '首页', '主页', '无障碍', '政务', '办事', '互动', 
            '走进', '移动版', '手机版', '导航', '菜单', '搜索', '市政府'
        ]
        
        # 尾部内容特征关键词
        footer_content_keywords = [
            '网站说明', '网站标识码', '版权所有', '主办单位', '承办单位', 
            '技术支持', '联系我们', '网站地图', '隐私政策', '免责声明',
            '备案号', 'icp', '公安备案', '政府网站', '网站管理'
        ]
        
        # 检查是否包含多个首部或尾部关键词
        header_count = sum(1 for keyword in header_content_keywords if keyword in div_text)
        footer_count = sum(1 for keyword in footer_content_keywords if keyword in div_text)
        
        if header_count >= 2 or footer_count >= 2:
            return div_element
    
    # 如果没有找到明显的结构特征容器，返回直接父级容器
    if element.getparent() and element.getparent().tag != 'html':
        return element.getparent()
    
    return None
def find_footer_container_by_traceback(element):
    """通过回溯找到footer容器"""
    current = element
    
    while current is not None:
        # 检查当前元素是否为容器
        if current.tag in ['div', 'section', 'footer']:
            # 检查容器特征
            classes = current.get('class', '').lower()
            elem_id = current.get('id', '').lower()
            
            # footer结构特征
            footer_indicators = ['footer', 'foot', 'bottom', 'end', 'copyright']
            for indicator in footer_indicators:
                if indicator in classes or indicator in elem_id:
                    return current
        
        # 检查是否到达顶层标签
        parent = current.getparent()
        if parent is None or parent.tag in ['html', 'head', 'body', 'script', 'meta']:
            break
            
        current = parent
    
    return None
def preprocess_html_remove_interference(page_tree):
    
    # 获取body元素
    body = page_tree.xpath("//body")[0] if page_tree.xpath("//body") else page_tree
    
    # 第一步：通过内容特征回溯删除首部和尾部容器
    body = remove_header_footer_by_content_traceback(body)
    
    # 第二步：识别并删除明显的页面级header/footer容器（原有逻辑）
    interference_containers = []
    
    # 查找所有可能的干扰容器
    all_containers = body.xpath(".//div | .//section | .//header | .//footer | .//nav | .//aside")
    
    for container in all_containers:
        if is_interference_container(container):
            interference_containers.append(container)
    
    # 删除干扰容器
    removed_count = 0
    for container in interference_containers:
        try:
            parent = container.getparent()
            if parent is not None:
                parent.remove(container)
                removed_count += 1
        except Exception as e:
            print(f"删除容器时出错: {e}")
    
    
    # 输出清理后的HTML到终端
    cleaned_html = html.tostring(body, encoding='unicode', pretty_print=True)
    print("\n=== 清理后的HTML内容 ===")
    print(cleaned_html[:2000] + "..." if len(cleaned_html) > 2000 else cleaned_html)
    print("=== HTML内容结束 ===\n")
    
    return body

def is_interference_container(container):
    """判断是否为需要删除的干扰容器"""
    classes = container.get('class', '').lower()
    elem_id = container.get('id', '').lower()
    tag_name = container.tag.lower()
    text_content = container.text_content().lower()
    
    # 强制删除的标签
    if tag_name in ['header', 'footer', 'nav']:
        return True
    
    # 强制删除的结构特征
    strong_interference_keywords = [
        'header', 'footer', 'nav', 'navigation', 'menu', 'menubar', 
        'topbar', 'bottom', 'sidebar', 'aside', 'banner'
    ]
    
    for keyword in strong_interference_keywords:
        if keyword in classes or keyword in elem_id:
            return True
    
    # 基于内容特征的删除判断
    # 页面级header内容特征
    header_content_patterns = [
        '登录', '注册', '首页', '主页', '无障碍', '政务服务', '办事服务',
        '互动交流', '走进', '移动版', '手机版', '导航', '菜单', '搜索',
        'login', 'register', 'home', 'menu', 'search', 'nav'
    ]
    
    # 页面级footer内容特征
    footer_content_patterns = [
        '网站说明', '网站标识码', '版权所有', '主办单位', '承办单位',
        '技术支持', '联系我们', '网站地图', '隐私政策', '免责声明',
        '备案号', 'icp', '公安备案', '政府网站', '网站管理',
        'copyright', 'all rights reserved', 'powered by'
    ]
    
    # 计算内容特征匹配度
    header_matches = sum(1 for pattern in header_content_patterns if pattern in text_content)
    footer_matches = sum(1 for pattern in footer_content_patterns if pattern in text_content)
    
    # 如果包含多个header或footer特征词，认为是干扰容器
    if header_matches >= 3:
        return True
    
    if footer_matches >= 3:
        return True
    
    # 检查容器大小和内容密度
    text_length = len(text_content.strip())
    child_count = len(container.xpath(".//*"))
    
    # 如果是小容器但包含很多链接，可能是导航
    links = container.xpath(".//a")
    if text_length < 500 and len(links) > 8:
        link_text_ratio = sum(len(link.text_content()) for link in links) / max(text_length, 1)
        if link_text_ratio > 0.6:  # 链接文本占比超过60%
            return True
    
    return False

def find_article_container(page_tree):
    cleaned_body = preprocess_html_remove_interference(page_tree)
    main_content = find_main_content_in_cleaned_html(cleaned_body)
    
    return main_content

def find_main_content_in_cleaned_html(cleaned_body):
    """在清理后的HTML中查找主内容区域"""
    
    # 获取所有可能的内容容器
    content_containers = cleaned_body.xpath(".//div | .//section | .//article | .//main")
    
    if not content_containers:
        print("未找到内容容器，返回body")
        return cleaned_body
    
    # 对容器进行评分
    scored_containers = []
    for container in content_containers:
        score = calculate_content_container_score(container)
        if score > 0:  # 只考虑正分容器
            scored_containers.append((container, score))
    
    if not scored_containers:
        print("未找到正分容器，返回第一个容器")
        return content_containers[0]
    
    # 选择得分最高的容器
    scored_containers.sort(key=lambda x: x[1], reverse=True)
    # best_container = scored_containers[0][0]
    # 选择了得分次一级的容器
    best_score = scored_containers[0][1]
    
    # ---------------------------------------------------------------------------------------------原方法，对于极为复杂的页面会定位的“过于准确”
    # same_score_containers = [container for container, score in scored_containers if score == best_score]
    # if len(same_score_containers) > 1:
    #     # 检查层级关系，层级关系。这一步直接影响结果的范围，对于某些范围大的页面，你可以考虑不获取最佳的，而获取次佳的容器 
    #     best_container = select_best_from_same_score_containers(same_score_containers)
    # else:
    #     best_container = scored_containers[0][0]
    # print(f"选择最佳内容容器，得分: {best_score}")
    # print(f"容器信息: {best_container.tag} class='{best_container.get('class', '')[:50]}'")
    # ---------------------------------------------------------------------------------------------
    # 设置分数阈值，考虑分数相近的容器（差距在20分以内）
    score_threshold = 20
    
    # 找出分数在阈值范围内的容器
    similar_score_containers = [(container, score) for container, score in scored_containers 
                               if abs(score - best_score) <= score_threshold]
    
    print(f"找到 {len(similar_score_containers)} 个分数相近的容器:")
    for i, (container, score) in enumerate(similar_score_containers):
        print(f"容器{i+1}: {container.tag} class='{container.get('class', '')}' 得分: {score}")
    
    # 如果有多个分数相近的容器，选择层级最深的
    if len(similar_score_containers) > 1:
        # best_container = select_deepest_container_from_similar([c for c, s in similar_score_containers])
        # 选择最优的
        best_container = select_best_container_prefer_child([c for c, s in similar_score_containers], scored_containers)
    else:
        best_container = scored_containers[0][0]
    # best_container = scored_containers[0][0]
    # 获取最终选择的容器分数
    final_score = next(score for container, score in scored_containers if container == best_container)
    print(f"最终选择容器，得分: {final_score}")
    print(f"容器信息: {best_container.tag} class='{best_container.get('class', '')}'")
    return best_container
def is_child_of(child_element, parent_element):
    """检查child_element是否是parent_element的子节点"""
    current = child_element.getparent()
    while current is not None:
        if current == parent_element:
            return True
        current = current.getparent()
    return False

def select_best_container_prefer_child(similar_containers, all_scored_containers):
    """从分数相近的容器中选择最佳的，优先选择子节点"""
    
    # 检查容器之间的父子关系
    parent_child_pairs = []
    
    for i, container1 in enumerate(similar_containers):
        for j, container2 in enumerate(similar_containers):
            if i != j:
                # 检查container2是否是container1的子节点
                if is_child_of(container2, container1):
                    # 获取两个容器的分数
                    score1 = next(score for c, score in all_scored_containers if c == container1)
                    score2 = next(score for c, score in all_scored_containers if c == container2)
                    parent_child_pairs.append((container1, container2, score1, score2))
                    print(f"发现父子关系: 父容器得分{score1}, 子容器得分{score2}")
    
    # 如果找到父子关系，需要更严格的判断
    if parent_child_pairs:
        # 找出所有符合条件的子节点（分数差距小于20分，更严格）
        valid_children = []
        for parent, child, parent_score, child_score in parent_child_pairs:
            score_diff = parent_score - child_score
            # 只有当子节点分数差距很小时才考虑选择子节点
            if score_diff <= 20 and child_score >= 150:  # 子节点本身分数要足够高
                valid_children.append((child, child_score, score_diff))
        
        if valid_children:
            # 按分数排序，选择分数最高的子节点
            valid_children.sort(key=lambda x: (-x[1], x[2]))  # 按子节点分数降序，分差升序
            
            best_child, best_score, score_diff = valid_children[0]
            
            # 额外检查：确保选择的子节点确实比父节点更精确
            # 检查子节点的内容密度是否更高
            child_text_length = len(best_child.text_content().strip())
            parent_candidates = [parent for parent, child, p_score, c_score in parent_child_pairs 
                               if child == best_child]
            
            if parent_candidates:
                parent = parent_candidates[0]
                parent_text_length = len(parent.text_content().strip())
                
                # 如果子节点的内容长度不到父节点的60%，可能选择了错误的子节点
                if child_text_length < parent_text_length * 0.6:
                    print(f"子节点内容过少({child_text_length} vs {parent_text_length})，选择父节点")
                    return parent
            
            print(f"选择子容器: {best_child.tag} class='{best_child.get('class', '')}' (父子分差: {score_diff})")
            return best_child
    
    # 如果没有合适的父子关系，使用原来的层级深度选择逻辑
    return select_deepest_container_from_similar(similar_containers)
def select_deepest_container_from_similar(similar_containers):
    """从分数相近的容器中选择层级最深的一个"""
    if not similar_containers:
        return None
    
    if len(similar_containers) == 1:
        return similar_containers[0]
    
    # 计算每个容器的层级深度
    container_depths = []
    for container in similar_containers:
        depth = calculate_container_depth(container)
        container_depths.append((container, depth))
        print(f"  候选容器层级深度: {depth} - {container.tag} class='{container.get('class', '')}'")
    
    # 按层级深度排序（深度越大，层级越深）
    container_depths.sort(key=lambda x: x[1], reverse=True)
    
    # 选择层级最深的容器
    deepest_container = container_depths[0][0]
    deepest_depth = container_depths[0][1]
    
    print(f"选择最深层容器 (深度 {deepest_depth}): {deepest_container.tag} class='{deepest_container.get('class', '')}'")
    return deepest_container

def calculate_container_depth(container):
    """计算容器距离body的层级深度"""
    depth = 0
    current = container
    
    # 向上遍历直到body或html
    while current is not None and current.tag not in ['body', 'html']:
        depth += 1
        current = current.getparent()
        if current is None:
            break
    
    return depth
def select_best_from_same_score_containers(containers):
    """从得分相同的多个容器中选择层级最深的一个（儿子容器）"""
    # 检查容器之间的层级关系，选择层级最深的
    container_depths = []
    
    for container in containers:
        # 计算容器的层级深度（距离body的层级数）
        depth = calculate_container_depth(container)
        container_depths.append((container, depth))
        
        print(f"容器层级深度: {depth} - {container.tag} class='{container.get('class', '')[:30]}'")
    
    # 按层级深度排序（深度越大，层级越深）
    container_depths.sort(key=lambda x: x[1], reverse=True)
    
    # 选择层级最深的容器（儿子容器）
    best_container = container_depths[0][0]
    best_depth = container_depths[0][1]
    
    print(f"选择层级最深的容器 (深度 {best_depth}): {best_container.tag} class='{best_container.get('class', '')[:30]}'")
    
    return best_container

def calculate_container_depth(container):
    """计算容器距离body的层级深度"""
    depth = 0
    current = container
    
    # 向上遍历直到body或html
    while current is not None and current.tag not in ['body', 'html']:
        depth += 1
        current = current.getparent()
        if current is None:
            break
    
    return depth
def calculate_content_container_score(container):
    """计算内容容器得分 - 专注于识别真正的内容区域"""
    score = 0
    debug_info = []
    
    classes = container.get('class', '').lower()
    elem_id = container.get('id', '').lower()
    text_content = container.text_content()
    text_length = len(text_content.strip())
    
    # 1. 基础内容长度评分
    if text_length > 1000:
        score += 50
        debug_info.append("长内容: +50")
    elif text_length > 500:
        score += 35
        debug_info.append("中等内容: +35")
    elif text_length > 200:
        score += 20
        debug_info.append("短内容: +20")
    elif text_length < 50:
        score -= 20
        debug_info.append("内容太少: -20")
    
    role = container.get('role', '').lower()
    if role == 'viewlist':
        debug_info.append(f"-----------------发现role------------------{role}")
        score += 150  # 大幅度加分
        debug_info.append("Role特征: +100 (role='viewlist')")
    elif role in ['list', 'listbox', 'grid']:
        score += 50  # 其他列表相关role也加分
        debug_info.append(f"Role特征: +50 (role='{role}')")
    # 2. 多样化内容特征检测（避免重复加分）
    content_indicators = [
        # 时间特征（合并所有时间相关）
        (r'\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日|\d{4}/\d{1,2}/\d{1,2}|发布时间|更新日期|发布日期|成文日期', 30, '时间特征'),
        # 公文特征（权重高）
        (r'通知|公告|意见|办法|规定|措施|方案|决定|指导|实施', 40, '公文特征'),
        # 条款特征（权重高）
        (r'第[一二三四五六七八九十\d]+条|第[一二三四五六七八九十\d]+章|第[一二三四五六七八九十\d]+节', 35, '条款特征'),
        # 政务信息特征（移除时间相关）
        (r'索引号|主题分类|发文机关|发文字号|有效性', 25, '政务信息'),
        # 附件特征
        (r'附件|下载|pdf|doc|docx|文件下载', 20, '附件特征'),
        # 内容结构特征
        (r'为了|根据|按照|依据|现将|特制定|现印发|请结合实际', 30, '内容结构')
    ]
    
    total_content_score = 0
    matched_features = []
    
    for pattern, weight, feature_name in content_indicators:
        if re.search(pattern, text_content):
            total_content_score += weight
            matched_features.append(feature_name)
    
    # 限制总的内容特征得分，但提高上限
    if total_content_score > 0:
        final_content_score = min(total_content_score, 120)  # 提高上限到120
        score += final_content_score
        debug_info.append(f"内容特征: +{final_content_score} ({','.join(matched_features)})")
    
    # 3. 正面类名/ID特征
    positive_keywords = [
        'content', 'main', 'article', 'news', 'data', 'info', 
        'detail', 'result', 'list', 'body', 'text'
    ]
    
    positive_matches = 0
    for keyword in positive_keywords:
        if keyword in classes or keyword in elem_id:
            positive_matches += 1
    
    if positive_matches > 0:
        positive_score = min(positive_matches * 20, 60)
        score += positive_score
        debug_info.append(f"正面特征: +{positive_score}")
    
    # 4. 结构化内容检测
    structured_elements = container.xpath(".//p | .//h1 | .//h2 | .//h3 | .//li | .//table")
    if len(structured_elements) > 5:
        structure_score = min(len(structured_elements) * 2, 40)
        score += structure_score
        debug_info.append(f"结构化内容: +{structure_score}")
    
    # 5. 图片内容
    images = container.xpath(".//img")
    if len(images) > 0:
        image_score = min(len(images) * 3, 20)
        score += image_score
        debug_info.append(f"图片内容: +{image_score}")
    
    # 6. 负面特征检测（剩余的干扰项）
    remaining_negative_keywords = [
        'sidebar', 'aside', 'related', 'recommend', 'ad', 'advertisement'
    ]
    
    for keyword in remaining_negative_keywords:
        if keyword in classes or keyword in elem_id:
            score -= 30
            debug_info.append(f"负面特征: -30 ({keyword})")
    
    # 输出调试信息
    container_info = f"{container.tag} class='{classes[:30]}'"
    print(f"容器评分: {score} - {container_info}")
    for info in debug_info[:4]:
        print(f"  {info}")
    
    return score

def exclude_page_header_footer(body):
    """排除页面级别的header和footer"""
    children = body.xpath("./div | ./main | ./section | ./article")
    
    if not children:
        return body
    
    valid_children = []
    for child in children:
        if not is_page_level_header_footer(child):
            valid_children.append(child)
    
    return find_middle_content(valid_children)

def is_page_level_header_footer(element):
    """判断是否是页面级别的header或footer - 更严格的检查"""
    classes = element.get('class', '').lower()
    elem_id = element.get('id', '').lower()
    tag_name = element.tag.lower()
    
    # 检查标签名
    if tag_name in ['header', 'footer', 'nav']:
        return True
    
    # 检查是否在footer区域
    is_footer, _ = is_in_footer_area(element)
    if is_footer:
        return True
    
    # 检查页面级别的header/footer特征
    page_keywords = ['header', 'footer', 'nav', 'menu', 'topbar', 'bottom', 'top']
    for keyword in page_keywords:
        if keyword in classes or keyword in elem_id:
            return True
    
    # 检查role属性
    role = element.get('role', '').lower()
    if role in ['banner', 'navigation', 'contentinfo']:
        return True
    
    return False

def find_middle_content(valid_children):
    """从有效子元素中找到中间的主要内容"""
    if not valid_children:
        return None
    
    if len(valid_children) == 1:
        return valid_children[0]
    
    # 计算每个容器的内容得分
    scored_containers = []
    for container in valid_children:
        score = calculate_content_richness(container)
        scored_containers.append((container, score))
    
    # 选择得分最高的容器
    scored_containers.sort(key=lambda x: x[1], reverse=True)
    best_container = scored_containers[0][0]
    
    print(f"页面主体容器得分: {scored_containers[0][1]}")
    return best_container

def calculate_content_richness(container):
    """计算容器的内容丰富度"""
    score = 0
    
    text_content = container.text_content().strip()
    content_length = len(text_content)
    
    if content_length > 1000:
        score += 40
    elif content_length > 500:
        score += 30
    elif content_length > 200:
        score += 20
    elif content_length > 100:
        score += 10
    else:
        return -5
    
    # 检查图片数量
    images = container.xpath(".//img")
    if len(images) > 0:
        score += min(len(images) * 3, 20)
    
    # 检查结构化内容
    structured_elements = container.xpath(".//p | .//div[contains(@style, 'text-align')] | .//h1 | .//h2 | .//h3")
    if len(structured_elements) > 0:
        score += min(len(structured_elements) * 2, 25)
    
    return score

def exclude_local_header_footer(container):
    """在容器内部排除局部的header和footer"""
    children = container.xpath("./div | ./section | ./article")
    
    if not children:
        return container
    
    valid_children = []
    for child in children:
        if not is_local_header_footer(child):
            valid_children.append(child)
    
    if not valid_children:
        return container
    
    return select_content_container(valid_children)

def is_local_header_footer(element):
    """判断是否是局部的header或footer"""
    classes = element.get('class', '').lower()
    elem_id = element.get('id', '').lower()
    
    # 检查局部header/footer特征
    local_keywords = ['title', 'tit', 'head', 'foot', 'top', 'bottom', 'nav', 'menu']
    for keyword in local_keywords:
        if keyword in classes or keyword in elem_id:
            # 进一步检查是否真的是header/footer
            text_content = element.text_content().strip()
            if len(text_content) < 200:  # 内容较少，可能是标题或导航
                return True
    
    return False

def select_content_container(valid_children):
    """从有效子容器中选择最佳的内容容器"""
    if len(valid_children) == 1:
        return valid_children[0]
    
    # 计算每个容器的得分
    scored_containers = []
    for container in valid_children:
        score = calculate_final_score(container)
        scored_containers.append((container, score))
    
    # 选择得分最高的容器
    scored_containers.sort(key=lambda x: x[1], reverse=True)
    best_container = scored_containers[0][0]
    
    return best_container

def calculate_final_score(container):
    """计算最终容器得分"""
    score = 0
    
    text_content = container.text_content().strip()
    content_length = len(text_content)
    
    if content_length > 500:
        score += 30
    elif content_length > 200:
        score += 20
    elif content_length > 100:
        score += 15
    else:
        score += 5
    
    # 检查图片
    images = container.xpath(".//img")
    if len(images) > 0:
        score += min(len(images) * 4, 25)
    
    # 检查结构化内容
    styled_divs = container.xpath(".//div[contains(@style, 'text-align')]")
    paragraphs = container.xpath(".//p")
    
    structure_count = len(styled_divs) + len(paragraphs)
    if structure_count > 0:
        score += min(structure_count * 2, 20)
    
    # 检查类名特征
    classes = container.get('class', '').lower()
    elem_id = container.get('id', '').lower()
    
    content_keywords = ['content', 'article', 'detail', 'main', 'body', 'text', 'editor', 'con']
    for keyword in content_keywords:
        if keyword in classes or keyword in elem_id:
            score += 15
    
    return score

def find_main_content_area(containers):
    """在有效容器中找到主内容区域"""
    candidates = []
    
    for container in containers:
        score = calculate_main_content_score(container)
        if score > 0:
            candidates.append((container, score))
    
    if not candidates:
        return None
    
    # 选择得分最高的作为主内容区域
    candidates.sort(key=lambda x: x[1], reverse=True)
    main_area = candidates[0][0]
    
    print(f"主内容区域得分: {candidates[0][1]}")
    return main_area

def calculate_main_content_score(container):
    """计算主内容区域得分"""
    score = 0
    
    text_content = container.text_content().strip()
    content_length = len(text_content)
    
    # 内容长度是主要指标
    if content_length > 500:
        score += 30
    elif content_length > 200:
        score += 20
    elif content_length > 100:
        score += 10
    else:
        return -5  # 内容太少
    
    # 检查是否包含丰富内容
    images = container.xpath(".//img")
    if len(images) > 0:
        score += min(len(images) * 2, 15)
    
    # 检查类名特征
    classes = container.get('class', '').lower()
    elem_id = container.get('id', '').lower()
    
    content_keywords = ['content', 'main', 'article', 'detail', 'body']
    for keyword in content_keywords:
        if keyword in classes or keyword in elem_id:
            score += 15
    
    return score


    
    # 检查类名
    classes = container.get('class', '').lower()
    if any(word in classes for word in ['content', 'article', 'detail', 'editor', 'text']):
        score += 15
    
    return score



def is_in_footer_area(element):
    """检查元素是否在footer区域"""
    current = element
    depth = 0
    while current is not None and depth < 10:  # 检查10层祖先
        classes = current.get('class', '').lower()
        elem_id = current.get('id', '').lower()
        tag_name = current.tag.lower()
        
        # 检查footer相关特征
        footer_indicators = [
            'footer', 'bottom', 'foot', 'end', 'copyright', 
            'links', 'sitemap', 'contact', 'about'
        ]
        
        for indicator in footer_indicators:
            if (indicator in classes or indicator in elem_id or 
                (tag_name == 'footer')):
                return True, f"发现footer特征: {indicator} (第{depth}层)"
        
        # 检查是否在页面底部区域（通过样式或位置判断）
        style = current.get('style', '').lower()
        if 'bottom' in style or 'fixed' in style:
            return True, f"发现底部样式 (第{depth}层)"
        
        current = current.getparent()
        depth += 1
    
    return False, ""

def find_list_container(page_tree):
    # 首先尝试使用改进的文章容器查找算法
    article_container = find_article_container(page_tree)
    if article_container is not None:
        return article_container    
    list_selectors = [
        "//li", "//tr", "//article",
        "//div[contains(@class, 'item')]",
        "//div[contains(@class, 'list')]",
        "//ul//li", "//ol//li", "//table//tr",
        "//section//ul[contains(@class, 'item')]",
        "//section//ul[contains(@class, 'list')]",
        "//section//div[contains(@class, 'list')]",
        "//section//div[contains(@class, 'item')]"
    ]
    
    def count_list_items(element):
        items = element.xpath(".//li | .//tr | .//article | .//div[contains(@class, 'item')]")
        return len(items)
    
    def calculate_container_score(container):
        """计算容器作为目标列表的得分 - 第一轮严格过滤首部尾部"""
        score = 0
        debug_info = []
        
        # 获取容器的基本信息
        classes = container.get('class', '').lower()
        elem_id = container.get('id', '').lower()
        role = container.get('role', '').lower()
        tag_name = container.tag.lower()
        text_content = container.text_content().lower()
        
        # 第一轮过滤：根据内容特征直接排除首部和尾部容器
        # 1. 检查首部特征内容
        header_content_keywords = [
            '登录', '注册', '首页', '主页', '无障碍', '政务', '办事', '互动', 
            '走进', '移动版', '手机版', '导航', '菜单', '搜索', '市政府',
            'login', 'register', 'home', 'menu', 'search', 'nav'
        ]
        
        header_content_count = 0
        for keyword in header_content_keywords:
            if keyword in text_content:
                header_content_count += 1
        
        # 如果包含多个首部关键词，严重减分
        if header_content_count >= 2:
            score -= 300  # 极严重减分，基本排除
            debug_info.append(f"首部内容特征: -300 (发现{header_content_count}个首部关键词)")
        
        # 2. 检查尾部特征内容
        footer_content_keywords = [
            '网站说明', '网站标识码', '版权所有', '主办单位', '承办单位', 
            '技术支持', '联系我们', '网站地图', '隐私政策', '免责声明',
            '备案号', 'icp', '公安备案', '政府网站', '网站管理',
            'copyright', 'all rights reserved', 'powered by', 'designed by'
        ]
        
        footer_content_count = 0
        for keyword in footer_content_keywords:
            if keyword in text_content:
                footer_content_count += 1
        
        # 如果包含多个尾部关键词，严重减分
        if footer_content_count >= 2:
            score -= 300  # 极严重减分，基本排除
            debug_info.append(f"尾部内容特征: -300 (发现{footer_content_count}个尾部关键词)")
        
        # 3. 检查结构特征 - footer/header标签和类名
        footer_structure_indicators = ['footer', 'foot', 'bottom', 'end', 'copyright', 'links', 'sitemap']
        for indicator in footer_structure_indicators:
            if (indicator in classes or indicator in elem_id or 
                indicator in role or tag_name == 'footer'):
                score -= 250  # 极严重减分
                debug_info.append(f"Footer结构特征: -250 (发现'{indicator}')")
        
        # 4. 检查header/nav结构特征
        header_structure_indicators = ['header', 'nav', 'navigation', 'menu', 'topbar', 'banner', 'menubar']
        for indicator in header_structure_indicators:
            if (indicator in classes or indicator in elem_id or 
                indicator in role or tag_name in ['header', 'nav','menu']):
                score -= 200  # 严重减分
                debug_info.append(f"Header结构特征: -200 (发现'{indicator}')")
        
        # 5. 检查祖先元素的负面特征（但权重降低，因为第一轮已经过滤了大部分）
        current = container
        depth = 0
        while current is not None and depth < 5:  # 减少检查层级
            parent_classes = current.get('class', '').lower()
            parent_id = current.get('id', '').lower()
            parent_tag = current.tag.lower()
            
            # 检查祖先的footer特征
            for indicator in footer_structure_indicators:
                if (indicator in parent_classes or indicator in parent_id or parent_tag == 'footer'):
                    penalty = max(60 - depth * 10, 15)  # 减少祖先特征的权重
                    score -= penalty
                    debug_info.append(f"祖先Footer: -{penalty} (第{depth}层'{indicator}')")
            
            # 检查祖先的header/nav特征
            for indicator in header_structure_indicators:
                if (indicator in parent_classes or indicator in parent_id or parent_tag in ['header', 'nav']):
                    penalty = max(50 - depth * 8, 12)  # 减少祖先特征的权重
                    score -= penalty
                    debug_info.append(f"祖先Header: -{penalty} (第{depth}层'{indicator}')")
            
            current = current.getparent()
            depth += 1
        
        # 如果已经是严重负分，直接返回，不需要继续计算
        if score < -150:
            return score
        
        # 6. 正面特征评分 - 专注于内容质量
        # 检查时间特征（强正面特征）
        precise_time_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{4}年\d{1,2}月\d{1,2}日',  # 完整的中文日期
            r'\d{4}/\d{1,2}/\d{1,2}',  # YYYY/MM/DD
            r'发布时间', r'更新日期', r'发布日期', r'创建时间'
        ]
        
        precise_matches = 0
        for pattern in precise_time_patterns:
            matches = len(re.findall(pattern, text_content))
            precise_matches += matches
        
        if precise_matches > 0:
            time_score = min(precise_matches * 30, 90)  # 增加时间特征权重
            score += time_score
            debug_info.append(f"时间特征: +{time_score} ({precise_matches}个匹配)")
        
        # 7. 检查内容长度和质量
        items = container.xpath(".//*[self::li or self::tr or self::article or self::div[contains(@class, 'item')]]")
        if items:
            total_length = sum(len(item.text_content().strip()) for item in items)
            avg_length = total_length / len(items) if items else 0
            
            if avg_length > 150:
                score += 40  # 增加长内容的权重
                debug_info.append(f"文本长度: +40 (平均{avg_length:.1f}字符)")
            elif avg_length > 80:
                score += 30
                debug_info.append(f"文本长度: +30 (平均{avg_length:.1f}字符)")
            elif avg_length > 40:
                score += 20
                debug_info.append(f"文本长度: +20 (平均{avg_length:.1f}字符)")
            elif avg_length < 20:  # 文本太短，可能是导航
                score -= 20
                debug_info.append(f"文本长度: -20 (平均{avg_length:.1f}字符，太短)")
        
        # 8. 检查正面结构特征
        strong_positive_indicators = ['content', 'main', 'news', 'article', 'data', 'info', 'detail', 'result', 'list']
        positive_score = 0
        for indicator in strong_positive_indicators:
            if indicator in classes or indicator in elem_id:
                positive_score += 25  # 增加正面特征权重
                debug_info.append(f"正面特征: +25 ('{indicator}')")
        
        score += min(positive_score, 75)  # 限制正面特征的最大加分
        
        # 9. 检查内容多样性（图片、链接等）
        images = container.xpath(".//img")
        links = container.xpath(".//a[@href]")
        
        if len(images) > 0:
            image_score = min(len(images) * 3, 20)
            score += image_score
            debug_info.append(f"图片内容: +{image_score} ({len(images)}张图片)")
        
        if len(links) > 5:  # 有足够的链接说明是内容区域
            link_score = min(len(links) * 2, 30)
            score += link_score
            debug_info.append(f"链接内容: +{link_score} ({len(links)}个链接)")
        
        # 10. 最后检查：避免导航类内容（但权重降低，因为第一轮已经过滤了大部分）
        if items and len(items) > 2:
            # 只检查明显的导航词汇，减少误判
            strong_nav_words = ['登录', '注册', '首页', '主页', '联系我们', '关于我们']
            nav_word_count = 0
            
            for item in items[:8]:  # 减少检查的项目数
                item_text = item.text_content().strip().lower()
                for nav_word in strong_nav_words:
                    if nav_word in item_text:
                        nav_word_count += 1
                        break
            
            checked_items = min(len(items), 8)
            if nav_word_count > checked_items * 0.4:  # 提高阈值，减少误判
                nav_penalty = 30  # 减少导航词汇的减分
                score -= nav_penalty
                debug_info.append(f"导航词汇: -{nav_penalty} ({nav_word_count}/{checked_items}个)")
        
        # 输出调试信息
        container_info = f"标签:{tag_name}, 类名:{classes[:30]}{'...' if len(classes) > 30 else ''}"
        if elem_id:
            container_info += f", ID:{elem_id[:20]}{'...' if len(elem_id) > 20 else ''}"
        
        print(f"容器评分: {score} - {container_info}")
        for info in debug_info[:6]:  # 显示更多调试信息
            print(f"  {info}")
        
        return score
    
    # 第一层：找到所有可能的列表项
    all_items = []
    for selector in list_selectors:
        items = page_tree.xpath(selector)
        all_items.extend(items)
    
    if not all_items:
        return None
    
    # 按照父元素分组，找到包含列表项的父元素
    parent_counts = {}
    for item in all_items:
        parent = item.getparent()
        if parent is not None:
            if parent not in parent_counts:
                parent_counts[parent] = 0
            parent_counts[parent] += 1
    
    if not parent_counts:
        return None
    
    # 筛选候选容器：至少包含3个列表项
    candidate_containers = [(parent, count) for parent, count in parent_counts.items() if count >= 3]
    
    # 如果没有符合条件的容器，降低门槛到2个列表项
    if not candidate_containers:
        candidate_containers = [(parent, count) for parent, count in parent_counts.items() if count >= 2]
    
    # 如果还是没有，返回包含最多列表项的容器
    if not candidate_containers:
        return max(parent_counts.items(), key=lambda x: x[1])[0]
    
    # 对候选容器进行评分并排序
    scored_containers = []
    for container, count in candidate_containers:
        score = calculate_container_score(container)
        
        # 额外检查：如果容器在footer区域，严重减分
        is_footer, footer_msg = is_in_footer_area(container)
        ancestry_penalty = 0
        
        if is_footer:
            ancestry_penalty += 50  # footer区域严重减分
        
        # 检查其他负面祖先特征 - 但权重降低，因为第一轮已经过滤了大部分
        def check_negative_ancestry(element):
            """检查元素及其祖先的负面特征"""
            penalty = 0
            current = element
            depth = 0
            while current is not None and depth < 4:  # 减少检查层级
                classes = current.get('class', '').lower()
                elem_id = current.get('id', '').lower()
                text_content = current.text_content().lower()
                
                # 检查结构特征
                negative_keywords = ['nav', 'menu', 'sidebar', 'header', 'topbar', 'navigation', 'head']
                for keyword in negative_keywords:
                    if keyword in classes or keyword in elem_id:
                        penalty += 20  # 减少祖先特征的权重
                
                # 检查内容特征（只在前2层检查）
                if depth < 2:
                    footer_content_keywords = ['网站说明', '网站标识码', '版权所有', '备案号']
                    header_content_keywords = ['登录', '注册', '首页', '无障碍']
                    
                    content_penalty = 0
                    for keyword in footer_content_keywords + header_content_keywords:
                        if keyword in text_content:
                            content_penalty += 15
                    
                    if content_penalty > 30:  # 如果包含多个关键词
                        penalty += content_penalty
                
                current = current.getparent()
                depth += 1
            return penalty
        
        ancestry_penalty += check_negative_ancestry(container)
        #最终分数
        final_score = score - ancestry_penalty
        
        scored_containers.append((container, final_score, count))
    
    # 按分数排序，但优先考虑分数而不是数量
    scored_containers.sort(key=lambda x: x[1], reverse=True)
    
    # 严格过滤负分容器 - 提高阈值，更严格地排除首部尾部
    positive_scored = [sc for sc in scored_containers if sc[1] > 0]  # 只接受正分容器
    
    if positive_scored:
        # 选择得分最高的正分容器
        best_container = positive_scored[0][0]
        max_items = parent_counts[best_container]
    else:
        # 如果没有正分容器，尝试稍微宽松的阈值
        moderate_scored = [sc for sc in scored_containers if sc[1] > -50]
        
        if moderate_scored:
            best_container = moderate_scored[0][0]
            max_items = parent_counts[best_container]
        else:
            # 最后手段：选择得分最高的（但很可能不理想）
            best_container = scored_containers[0][0]
            max_items = parent_counts[best_container]
    
    # 逐层向上搜索优化容器
    current_container = best_container
    while True:
        parent = current_container.getparent()
        if parent is None or parent.tag == 'html':
            break
        
        # 检查父级元素是否包含footer等负面特征 - 更严格的检查
        def has_negative_ancestor(element):
            """检查元素的祖先是否包含负面特征 - 包括内容特征"""
            current = element
            depth = 0
            while current is not None and depth < 3:  # 检查3层祖先
                parent_classes = current.get('class', '').lower()
                parent_id = current.get('id', '').lower()
                parent_tag = current.tag.lower()
                parent_text = current.text_content().lower()
                
                # 检查结构负面关键词
                structure_negative = ['footer', 'nav', 'menu', 'sidebar', 'header', 'topbar', 'navigation', 'foot', 'head']
                for keyword in structure_negative:
                    if (keyword in parent_classes or keyword in parent_id or parent_tag in ['footer', 'header', 'nav']):
                        return True
                
                # 检查内容负面特征（只在前2层检查，避免过度检查）
                if depth < 2:
                    # 首部内容特征
                    header_content = ['登录', '注册', '首页', '主页', '无障碍', '政务', '办事', '互动', '走进']
                    header_count = sum(1 for word in header_content if word in parent_text)
                    
                    # 尾部内容特征
                    footer_content = ['网站说明', '网站标识码', '版权所有', '备案号', 'icp', '主办单位', '承办单位']
                    footer_count = sum(1 for word in footer_content if word in parent_text)
                    
                    # 如果包含多个首部或尾部关键词，认为是负面祖先
                    if header_count >= 2:
                        return True
                    if footer_count >= 2:
                        return True
                
                current = current.getparent()
                depth += 1
            return False
        
        # 如果父元素或其祖先包含负面特征，停止向上搜索
        if has_negative_ancestor(parent):
            print("父级包含负面特征，停止向上搜索")
            break
            
        # 计算父元素中的列表项数量
        parent_items = count_list_items(parent)
        
        # 检查父元素是否更适合作为容器
        parent_score = calculate_container_score(parent)
        current_score = calculate_container_score(current_container)
        
        print(f"比较得分: 当前={current_score}, 父级={parent_score}")
        print(f"项目数量: 当前={max_items}, 父级={parent_items}")
        
        should_upgrade = False
        
        # 首先检查父级是否有严重的负面特征
        if parent_score < -50:
            print(f"父级得分过低({parent_score})，跳过升级")
        else:
            # 条件1：父级得分明显更高且为正分
            if parent_score > current_score + 15 and parent_score > 10:
                should_upgrade = True
                print("父级得分明显更高且为正分，升级")
            
            # 条件2：父级得分相近且为正分，包含合理数量的项目
            elif (parent_score >= current_score - 3 and 
                  parent_score > 5 and  # 要求父级必须是正分
                  parent_items <= max_items * 2 and  # 更严格的项目数量限制
                  parent_items >= max_items):
                should_upgrade = True
                print("父级得分相近且为正分，升级")
            
            # 条件3：当前容器项目太少，父级有合理数量且得分不错
            elif (max_items < 4 and 
                  parent_items >= max_items and 
                  parent_items <= 15 and 
                  parent_score > 0):  # 要求父级必须是正分
                should_upgrade = True
                print("当前容器项目太少，升级到正分父级")
        
        if should_upgrade:
            current_container = parent
            max_items = parent_items
            print("升级到父级容器")
        else:
            print("保持当前容器")
            break
        
        # 安全检查：如果父级项目数量过多，停止
        if parent_items > 50:
            print(f"父级项目数量过多({parent_items})，停止向上搜索")
            break
    
    # 最终验证：确保选择的容器包含足够的列表项且不是首部尾部
    final_items = count_list_items(current_container)
    final_score = calculate_container_score(current_container)
    print(f"最终容器包含 {final_items} 个列表项，得分: {final_score}")
    
    # 如果最终容器项目太少且得分不好，尝试向上找一层
    if final_items < 4 or final_score < -10:
        parent = current_container.getparent()
        if parent is not None and parent.tag != 'html':
            parent_items = count_list_items(parent)
            parent_score = calculate_container_score(parent)
            
            # 更严格的条件：父级必须有更多项目且得分为正分
            if (parent_items > final_items and 
                parent_score > 0 and  # 要求正分
                parent_items <= 30):  # 避免选择过大的容器
                print(f"最终调整：选择正分父级容器 (项目数: {parent_items}, 得分: {parent_score})")
                current_container = parent
            else:
                print(f"父级不符合条件 (项目数: {parent_items}, 得分: {parent_score})，保持当前选择")
    
    return current_container
def generate_xpath(element):
    if not element:
        return None

    tag = element.tag

    # 1. 优先使用ID（如果存在且不是干扰特征）
    elem_id = element.get('id')
    if elem_id and not is_interference_identifier(elem_id):
        return f"//{tag}[@id='{elem_id}']"

    # 2. 使用类名（过滤干扰类名）
    # classes = element.get('class')
    # if classes:
    #     class_list = [cls.strip() for cls in classes.split() if cls.strip()]
    #     # 过滤掉干扰类名
    #     clean_classes = [cls for cls in class_list if not is_interference_identifier(cls)]
    #     if clean_classes:
    #         # 选择最长的干净类名
    #         longest_class = max(clean_classes, key=len)
    #         return f"//{tag}[contains(concat(' ', normalize-space(@class), ' '), ' {longest_class} ')]"
    classes = element.get('class')
    if classes:
        # 使用完整的class值，不进行过滤处理
        return f"//{tag}[@class='{classes}']"

    # 3. 使用其他属性（如 aria-label 等）
    for attr in ['aria-label', 'role', 'data-testid', 'data-role']:
        attr_value = element.get(attr)
        if attr_value and not is_interference_identifier(attr_value):
            return f"//{tag}[@{attr}='{attr_value}']"

    # 4. 尝试找到最近的有干净标识符的祖先
    def find_closest_clean_identifier(el):
        parent = el.getparent()
        while parent is not None and parent.tag != 'html':
            # 检查ID
            parent_id = parent.get('id')
            if parent_id and not is_interference_identifier(parent_id):
                return parent
            
            # 检查类名
            parent_classes = parent.get('class')
            if parent_classes:
                parent_class_list = [cls.strip() for cls in parent_classes.split() if cls.strip()]
                clean_parent_classes = [cls for cls in parent_class_list if not is_interference_identifier(cls)]
                if clean_parent_classes:
                    return parent
            parent = parent.getparent()
        return None

    ancestor = find_closest_clean_identifier(element)
    if ancestor is not None:
        # 生成祖先的 XPath
        ancestor_xpath = generate_xpath(ancestor)
        if ancestor_xpath:
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

def is_interference_identifier(identifier):
    """判断标识符是否包含干扰特征"""
    if not identifier:
        return False
    
    identifier_lower = identifier.lower()
    
    # 干扰关键词
    interference_keywords = [
        'header', 'footer', 'nav', 'navigation', 'menu', 'menubar',
        'topbar', 'bottom', 'sidebar', 'aside', 'banner', 'ad'
    ]
    
    for keyword in interference_keywords:
        if keyword in identifier_lower:
            return True
    
    return False

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
from DrissionPage import ChromiumPage
import json
def process_name(name_str):
    """处理name字段：去除js+智能分割标签"""
    # 1. 去除所有'js'子串（全局替换）
    cleaned_name = name_str.replace('js', '')
    
    # 2. 智能选择分隔符（优先>，其次-）
    separator = '>' if '>' in cleaned_name else '-'
    
    # 3. 分割标签并过滤空值
    return [tag.strip() for tag in cleaned_name.split(separator) if tag.strip()]

def get_html_content_Drission(name, url):
    tab_list = process_name(name)
    if not tab_list:
        print("警告：未解析出有效标签")
        return {"html": "", "xpathList4Click": []}

    page = ChromiumPage()
    xpathList4Click = []
    
    try:
        page.get(url)
        
        for i, tab_text in enumerate(tab_list):
            print(f"正在处理标签: {tab_text}")

            xpath_strategies = [
                f'xpath: //body//*[contains(text(),"{tab_text}") and name()!="script"]',
                f'xpath: //*[normalize-space()="{tab_text}"]',  # 完全匹配文本（忽略首尾空格）
                f'xpath: //*[contains(text(), "{tab_text}")]',  # 部分匹配文本
                f'xpath: //a[normalize-space()="{tab_text}"]',  # 限定在<a>标签
                f'xpath: //button[normalize-space()="{tab_text}"]',  # 限定在<button>标签
                f'xpath: //*[@title="{tab_text}"]',  # 通过title属性匹配
                f'xpath: //*[@data-name="{tab_text}"]',  # 通过data属性匹配
            ]     
            tab_element = None
            for strategy in xpath_strategies:
                if not tab_element:
                    try:
                        tab_element = page.ele(strategy, timeout=5)
                        if tab_element:
                            print(f"使用策略找到元素: {strategy}")
                            break
                    except Exception:
                        continue
            
            if tab_element:
                # 获取稳健XPath并点击
                tab_xpath = get_robust_xpath(tab_element)
                xpathList4Click.append(tab_xpath)
                tab_element.click(by_js=True)
                print(f"已点击({i+1}/{len(tab_list)}): {tab_text} - XPath: {tab_xpath}")
                
                # 等待加载
                page.wait.load_start()
                page.wait(3)  # 稳定等待
            else:
                print(f"⚠️ 未找到标签: '{tab_text}'，跳过后续操作")
                break

        # 获取渲染后的HTML
        rendered_html = page.html
        
        return  rendered_html,xpathList4Click
        
    except Exception as e:
        print(f"操作出错: {str(e)}")
        
        return html,xpathList4Click
    
    finally:
        page.quit()
        print("浏览器已关闭")

def process_entry(entry, max_retries=3):
    """处理单个条目"""
    url = entry['url']
    name = entry['name']
    xpathList4Click = ""
    print(f"\n处理: {entry['name']}")
    print(f"URL: {url}")
    if name.endswith('js'):
        print("JS页面")
        html_content,xpathList4Click = get_html_content_Drission(name,url)
    else :
        print("非JS页面")
        # 有100%可以获取的方法就不要换成可能出风险的方法，慢一点就慢一点，准确率最重要
        html_content = get_html_content_Selenium(url)

    # html_content = get_html_content(url)
    
    if not html_content:
        print("\nHtml content获取失败")
        return {**entry, 'xpath': None, 'status': 'failed'}
        
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
        if xpathList4Click:
            print(f"✓ 最终XPath: {best_xpath} (点击列表: {xpathList4Click})")
            return {**entry, 'xpath': best_xpath, 'status': 'success', 'xpathList4Click': xpathList4Click}
        else :
            print(f"✓ 最终XPath: {best_xpath}")
            return {**entry, 'xpath': best_xpath, 'status': 'success', 'xpathList4Click': None}
    
    print("✗ 未能找到有效XPath")
    return {**entry, 'xpath': None, 'status': 'failed','xpathList4Click': None}

def parse_input_file(input_file):
    """解析输入文件"""
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
    """写入输出文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            output_data = {
                'name': result['name'],
                'url': result['url'],
                'xpath': result.get('xpath', '')  
            }
            if result.get('xpathList4Click'):
                output_data['xpathList4Click'] = result['xpathList4Click']
            f.write("---\n")  
            f.write(f"name: {output_data['name']}\n")
            f.write(f"url: {output_data['url']}\n")
            f.write(f"xpath: \"{output_data['xpath']}\"\n")
            if 'xpathList4Click' in output_data and output_data['xpathList4Click']:
                f.write("xpathList4Click:\n")
                for xpath in output_data['xpathList4Click']:
                    safe_xpath = xpath.replace('"', '\\"').replace('\n', '\\n')
                    f.write(f"  - \"{safe_xpath}\"\n")
            else:
                f.write("xpathList4Click: []\n")
            

def process_entries_parallel(entries, max_workers=1):
    """并行处理多个条目"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_entry, entries))
    return results

def process_yml_file(input_file, output_file):
    """处理YML文件"""
    entries = parse_input_file(input_file)
    total = len(entries)
    
    if total == 0:
        print("未找到有效条目")
        return
    
    print(f"找到 {total} 个待处理条目")
    
    # 使用并行处理
    results = process_entries_parallel(entries)
    
    # 写入结果
    write_output_file(results, output_file)
    
    # 生成统计报告
    success_count = sum(1 for r in results if r.get('status') == 'success')
    failure_count = total - success_count
    
    print(f"\n处理完成: {success_count} 成功, {failure_count} 失败")
    print(f"结果已保存至: {output_file}")


import os
import glob
if __name__ == "__main__":
    try:
        
        input_file = "test.yml"    # 输入文件路径
        output_file = "testout.yml"  # 输出文件路径
        
        process_yml_file(input_file, output_file)


        # input_folder = "waitprocess"
        # output_folder = "processed"  
        
        # if not os.path.exists(output_folder):
        #     os.makedirs(output_folder)
        
        # files = glob.glob(os.path.join(input_folder, "*.yml"))
        
        # for input_file in files:
        #     base_name = os.path.basename(input_file)  
        #     output_file = os.path.join(output_folder, base_name)
        #     process_yml_file(input_file, output_file)
    finally:
        driver_pool.close_all()


# version1.0 

# 一个页面中，存在k个列表，假定k=3，有三个列表，列表1为导航栏，里面有8个列表项，列表2为侧边栏，里面有5个列表项，列表3是事项列表，里面有7个列表项，
# 此时，我的代码会把列表1作为目标获取，但实际情况应该是列表3才是正确的，这怎么办呢，
# 目前对于目标列表3，可能存在以下特点：里面往往存在时间字符串，并且有些页面中的文字的长度是大于列表1和列表2的。
# 除此之外，对于列表1，也有以下特点：当我们误获取这个列表1的时候，会去处理组装他的xpath，这个xpath里面往往是存在nav三个字母的，
# 在我的观察下，大部分情况中，只要xpath里面包含nav，那就很大可能说明获取失败了，没有获取到列表3，而是获取到了列表1

# 对于js页面，name中名称一定要准确，并且！name要尽量要少一点，比如“法定主动公开内容”，这个就写“法定”即可，这俩字有代表性，不能写“内容”这俩字，没有任何的代表性


# version2.0
# 2025.8.22
# 修改部分算法的逻辑，可以提取正文所在容器，而不是v1.0中提取列表，目前算法用于定位页面的主体内容，通过不断的去排除头部导航和底部footer来逐渐的定位主体。但是，对于页面中内容是一大串的文字，或者是图片，这种情况下密度算法将会失效，我们需要尽可能的排除主HTML中head和footer（就是页面的导航栏和底部栏，这两个里面可能存在大量的列表或者一大串的文字）
# 获取到的次HTML即为排除了干扰项的HTML内容，我们需要的container可能就存在于此，对于这个次级HTML，我们需要再一次的进行过滤，排除里面的header和footer，然后逐步缩小，但是不要精确，因为过于精确的获取容器会导致出现疏漏。

# 对于算法的进一步修改，需要判断出一个合理的权重，即扣分标准。首先！一定是扣分的居多，加分的少，对于可能是底部或者首部的内容，要大量的减分，应该算法的主要思路就是排除干扰项！

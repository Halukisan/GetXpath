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
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None

def get_html_content_Selenium(url, max_retries=3):
    """使用 Selenium 获取页面内容"""
    for attempt in range(max_retries):
        driver = None
        try:
            driver = driver_pool.get_driver()
            driver.set_page_load_timeout(180)
            driver.set_script_timeout(180)
            
            driver.get(url)
            time.sleep(10)
            
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
def find_article_container(page_tree):
    """通用文章内容容器查找"""
    
    all_divs = page_tree.xpath("//div")
    candidates = []
    
    for div in all_divs:
        is_footer, _ = is_in_footer_area(div)
        if is_footer:
            continue
            
        score = calculate_article_score(div)
        if score > 20:
            candidates.append((div, score))
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_container = candidates[0][0]
    
    print(f"文章容器得分: {candidates[0][1]}")
    return best_container

def calculate_article_score(container):
    score = 0
    
    text_content = container.text_content().strip()
    content_length = len(text_content)
    
    if content_length < 50:
        return -10
    
    images = container.xpath(".//img")
    styled_divs = container.xpath(".//div[contains(@style, 'text-align') or contains(@style, 'font-size')]")
    paragraphs = container.xpath(".//p")
    
    if content_length > 1000:
        score += 30
    elif content_length > 500:
        score += 20
    elif content_length > 200:
        score += 15
    else:
        score += 5
    
    if len(images) > 5:
        score += 30
    elif len(images) > 0:
        score += len(images) * 3
    
    structure_count = len(styled_divs) + len(paragraphs)
    if structure_count > 10:
        score += 20
    elif structure_count > 5:
        score += 15
    elif structure_count > 0:
        score += 10
    
    centered_content = container.xpath(".//div[contains(@style, 'text-align: center')]")
    if len(centered_content) > 0:
        score += 15
    
    classes = container.get('class', '').lower()
    elem_id = container.get('id', '').lower()
    
    positive_words = ['content', 'article', 'detail', 'main', 'body', 'text', 'editor']
    negative_words = ['nav', 'menu', 'sidebar', 'header', 'footer', 'ad', 'banner']
    
    for word in positive_words:
        if word in classes or word in elem_id:
            score += 10
    
    for word in negative_words:
        if word in classes or word in elem_id:
            score -= 25
    
    child_divs = container.xpath("./div")
    if len(child_divs) == 1 and content_length < 100:
        score -= 10
    
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
    article_container = find_article_container(page_tree)
    if article_container is not None:
        print("找到文章内容容器")
        return article_container
    
    print("未找到文章内容容器，尝试查找列表容器")
    
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
        """计算容器作为目标列表的得分"""
        score = 0
        debug_info = []  # 用于调试信息
        
        # 1. 检查是否包含时间字符串（目标列表特征）- 修正逻辑
        text_content = container.text_content().lower()
        
        # 更精确的时间模式，避免误匹配footer中的版权年份
        precise_time_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{4}年\d{1,2}月\d{1,2}日',  # 完整的中文日期
            r'\d{4}/\d{1,2}/\d{1,2}',  # YYYY/MM/DD
            r'发布时间', r'更新日期', r'发布日期', r'创建时间'
        ]
        
        # 可能误匹配的简单模式（需要额外验证）
        simple_patterns = [r'年', r'月', r'日']
        
        precise_matches = 0
        simple_matches = 0
        
        for pattern in precise_time_patterns:
            matches = len(re.findall(pattern, text_content))
            precise_matches += matches
        
        for pattern in simple_patterns:
            matches = len(re.findall(pattern, text_content))
            simple_matches += matches
        
        # 时间特征评分逻辑修正
        if precise_matches > 0:
            # 精确时间模式，直接加分
            time_score = min(precise_matches * 20, 60)
            score += time_score
            debug_info.append(f"精确时间特征: +{time_score} ({precise_matches}个匹配)")
        elif simple_matches > 3:
            # 简单模式需要多个匹配才加分，避免footer中的单个"年"字
            time_score = min((simple_matches - 3) * 10, 30)
            score += time_score
            debug_info.append(f"简单时间特征: +{time_score} ({simple_matches}个匹配)")
        elif simple_matches <= 2:
            # 很少的年月日字符，可能是footer版权信息，轻微减分
            score -= 2
            debug_info.append(f"疑似版权信息: -2 ({simple_matches}个年月日字符)")
        
        # 2. 检查平均文本长度（目标列表通常有较长文本）
        items = container.xpath(".//*[self::li or self::tr or self::article or self::div[contains(@class, 'item')]]")
        if items:
            total_length = sum(len(item.text_content().strip()) for item in items)
            avg_length = total_length / len(items)
            if avg_length > 80:  # 平均文本长度超过80字符
                score += 15
                debug_info.append(f"文本长度: +15 (平均{avg_length:.1f}字符)")
            elif avg_length > 50:  # 平均文本长度超过50字符
                score += 10
                debug_info.append(f"文本长度: +10 (平均{avg_length:.1f}字符)")
            elif avg_length > 30:
                score += 6
                debug_info.append(f"文本长度: +6 (平均{avg_length:.1f}字符)")
            elif avg_length > 15:
                score += 3
                debug_info.append(f"文本长度: +3 (平均{avg_length:.1f}字符)")
            elif avg_length < 10:  # 文本太短，可能是导航
                score -= 8
                debug_info.append(f"文本长度: -8 (平均{avg_length:.1f}字符，太短)")
        
        # 3. 检查是否包含导航特征（导航栏通常有这些特征）
        xpath = generate_xpath(container).lower() if container is not None else ""
        navigation_keywords = ['nav', 'menu', 'sidebar', 'breadcrumb', 'pagination']
        for keyword in navigation_keywords:
            if keyword in xpath:
                score -= 25  # 大幅减分
                debug_info.append(f"XPath导航特征: -25 (发现'{keyword}')")
        
        # 4. 检查类名和ID特征
        classes = container.get('class', '').lower()
        elem_id = container.get('id', '').lower()
        role = container.get('role', '').lower()
        
        # 负面特征（导航/页眉/页脚） - 更严格的检测
        negative_indicators = [
            'nav', 'menu', 'sidebar', 'header', 'footer', 'topbar', 'navigation',
            'breadcrumb', 'pagination', 'toolbar', 'menubar', 'banner', 'aside'
        ]
        
        for indicator in negative_indicators:
            # 检查完整单词匹配和常见变体
            patterns = [
                rf'\b{indicator}\b',  # 完整单词
                rf'{indicator}[-_]',  # 带分隔符
                rf'[-_]{indicator}',  # 前缀分隔符
                rf'{indicator}\d+',   # 带数字后缀
            ]
            
            for pattern in patterns:
                if re.search(pattern, classes):
                    score -= 20  # 类名中发现导航特征，大幅减分
                    debug_info.append(f"负面类名: -20 ('{indicator}')")
                if re.search(pattern, elem_id):
                    score -= 20  # ID中发现导航特征，大幅减分
                    debug_info.append(f"负面ID: -20 ('{indicator}')")
            
            if indicator in role:
                score -= 25  # role属性中发现导航特征，严重减分
                debug_info.append(f"负面role: -25 ('{indicator}')")
        
        # 5. 检查是否在页面底部（footer区域）
        # 通过检查父级元素是否包含footer相关信息
        current = container
        depth = 0
        while current is not None and depth < 5:  # 检查5层父级
            parent_classes = current.get('class', '').lower()
            parent_id = current.get('id', '').lower()
            
            if 'footer' in parent_classes or 'footer' in parent_id:
                score -= 30  # 在footer区域，严重减分
                debug_info.append("Footer区域: -30")
                break
            
            current = current.getparent()
            depth += 1
        
        # 正面特征（内容/列表/主体） - 更精确的匹配，避免误匹配导航
        # 高可信度的正面特征
        strong_positive_indicators = [
            'content', 'main', 'news', 'article', 'data', 'info', 'detail', 'result'
        ]
        
        # 可能误匹配的特征，需要额外检查
        weak_positive_indicators = [
            'list', 'item', 'container', 'body', 'section', 'con'
        ]
        
        # 检查高可信度正面特征
        for indicator in strong_positive_indicators:
            patterns = [
                rf'\b{indicator}\b',  # 完整单词
                rf'{indicator}[-_]',  # 带分隔符
                rf'[-_]{indicator}',  # 前缀分隔符
            ]
            
            for pattern in patterns:
                if re.search(pattern, classes):
                    score += 15  # 高可信度特征，更多加分
                    debug_info.append(f"强正面类名: +15 ('{indicator}')")
                if re.search(pattern, elem_id):
                    score += 15  # 高可信度特征，更多加分
                    debug_info.append(f"强正面ID: +15 ('{indicator}')")
        
        # 检查可能误匹配的正面特征
        for indicator in weak_positive_indicators:
            patterns = [
                rf'\b{indicator}\b',
                rf'{indicator}[-_]',
                rf'[-_]{indicator}',
            ]
            
            for pattern in patterns:
                if re.search(pattern, classes):
                    # 检查是否与负面特征组合（如nav-list, menu-item）
                    negative_combo = any(neg in classes for neg in ['nav', 'menu', 'sidebar', 'header', 'footer'])
                    if negative_combo:
                        score -= 5  # 负面组合，减分
                        debug_info.append(f"负面组合: -5 ('{indicator}'与导航特征组合)")
                    else:
                        score += 8  # 单独出现，适度加分
                        debug_info.append(f"弱正面类名: +8 ('{indicator}')")
                        
                if re.search(pattern, elem_id):
                    negative_combo = any(neg in elem_id for neg in ['nav', 'menu', 'sidebar', 'header', 'footer'])
                    if negative_combo:
                        score -= 5
                        debug_info.append(f"负面组合ID: -5 ('{indicator}'与导航特征组合)")
                    else:
                        score += 8
                        debug_info.append(f"弱正面ID: +8 ('{indicator}')")
        
        # 6. 检查列表项的多样性和长度（内容列表通常有更多样且更长的文本）
        if items and len(items) > 2:
            unique_texts = set()
            short_texts = 0  # 统计短文本数量
            
            for item in items[:10]:  # 只检查前10个避免性能问题
                text = item.text_content().strip()
                if text:
                    # 检查文本长度
                    if len(text) < 15:  # 短文本，可能是导航项
                        short_texts += 1
                    
                    # 用于多样性检查，取前30字符
                    unique_texts.add(text[:30])
            
            checked_items = min(len(items), 10)
            diversity_ratio = len(unique_texts) / checked_items if checked_items > 0 else 0
            short_ratio = short_texts / checked_items if checked_items > 0 else 0
            
            # 多样性评分
            if diversity_ratio > 0.8:  # 高多样性，可能是内容列表
                score += 10
                debug_info.append(f"文本多样性: +10 (比例{diversity_ratio:.2f})")
            elif diversity_ratio < 0.4:  # 低多样性，可能是重复的导航项
                score -= 8
                debug_info.append(f"文本多样性: -8 (比例{diversity_ratio:.2f}，重复性高)")
            
            # 短文本比例评分
            if short_ratio > 0.7:  # 大部分都是短文本，可能是导航
                score -= 12
                debug_info.append(f"短文本比例: -12 (比例{short_ratio:.2f}，可能是导航)")
            elif short_ratio < 0.3:  # 大部分都是长文本，可能是内容
                score += 8
                debug_info.append(f"短文本比例: +8 (比例{short_ratio:.2f}，文本较长)")
            
            # 8. 检查是否包含典型的导航菜单词汇
            navigation_words = [
                '首页', '主页', '新闻', '产品', '服务', '关于', '联系', '登录', '注册',
                'home', 'news', 'about', 'contact', 'login', 'register', 'product', 'service'
            ]
            
            nav_word_count = 0
            for item in items[:10]:
                item_text = item.text_content().strip().lower()
                for nav_word in navigation_words:
                    if nav_word in item_text:
                        nav_word_count += 1
                        break  # 每个item只计算一次
            
            if nav_word_count > checked_items * 0.4:  # 超过40%包含导航词汇
                score -= 15
                debug_info.append(f"导航词汇: -15 ({nav_word_count}/{checked_items}个包含导航词汇)")
        
        # 7. 检查链接比例（需要重新评估逻辑）
        links = container.xpath(".//a")
        if items and len(items) > 0:
            link_ratio = len(links) / len(items)
            
            # 修正逻辑：导航菜单通常链接比例很高（接近100%）
            # 内容列表通常有适中的链接比例（30-80%）
            if link_ratio > 0.9:  # 链接比例过高，可能是导航菜单
                score -= 10
                debug_info.append(f"链接比例: -10 (比例{link_ratio:.2f}，可能是导航)")
            elif 0.3 <= link_ratio <= 0.8:  # 适中的链接比例，可能是内容列表
                score += 5
                debug_info.append(f"链接比例: +5 (比例{link_ratio:.2f}，适中)")
            elif link_ratio < 0.1:  # 很少链接，可能不是列表
                score -= 3
                debug_info.append(f"链接比例: -3 (比例{link_ratio:.2f}，链接太少)")
        
        # 输出调试信息
        container_info = f"类名: {classes[:50]}..." if len(classes) > 50 else f"类名: {classes}"
        if elem_id:
            container_info += f", ID: {elem_id}"
        print(f"容器评分: {score} - {container_info}")
        for info in debug_info:
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
            print(f"容器在footer区域: {footer_msg}")
        
        # 检查其他负面祖先特征
        def check_negative_ancestry(element):
            """检查元素及其祖先的负面特征"""
            penalty = 0
            current = element
            depth = 0
            while current is not None and depth < 6:
                classes = current.get('class', '').lower()
                elem_id = current.get('id', '').lower()
                
                negative_keywords = ['nav', 'menu', 'sidebar', 'header', 'topbar', 'navigation']
                for keyword in negative_keywords:
                    if keyword in classes or keyword in elem_id:
                        penalty += 20  # 每发现一个负面特征减20分
                        print(f"发现祖先负面特征: {keyword} (第{depth}层)")
                
                current = current.getparent()
                depth += 1
            return penalty
        
        ancestry_penalty += check_negative_ancestry(container)
        final_score = score - ancestry_penalty
        
        scored_containers.append((container, final_score, count))
    
    # 按分数排序，但优先考虑分数而不是数量
    scored_containers.sort(key=lambda x: x[1], reverse=True)
    
    # 过滤掉明显的负分容器（很可能是导航/footer）
    positive_scored = [sc for sc in scored_containers if sc[1] > -15]  # 提高阈值
    
    if positive_scored:
        # 选择得分最高的正分容器
        best_container = positive_scored[0][0]
        max_items = parent_counts[best_container]
        print(f"选择容器得分: {positive_scored[0][1]}, 项目数: {positive_scored[0][2]}")
    else:
        # 如果所有容器都是负分，选择得分最高的（最不坏的）
        best_container = scored_containers[0][0]
        max_items = parent_counts[best_container]
        print(f"所有容器都是负分，选择最佳: {scored_containers[0][1]}, 项目数: {scored_containers[0][2]}")
    
    # 逐层向上搜索优化容器
    current_container = best_container
    while True:
        parent = current_container.getparent()
        if parent is None or parent.tag == 'html':
            break
        
        # 检查父级元素是否包含footer等负面特征
        def has_negative_ancestor(element):
            """检查元素的祖先是否包含负面特征"""
            current = element
            depth = 0
            while current is not None and depth < 8:  # 检查8层祖先
                parent_classes = current.get('class', '').lower()
                parent_id = current.get('id', '').lower()
                
                # 检查负面关键词
                negative_keywords = ['footer', 'nav', 'menu', 'sidebar', 'header', 'topbar', 'navigation']
                for keyword in negative_keywords:
                    if keyword in parent_classes or keyword in parent_id:
                        print(f"发现负面祖先: {keyword} 在第{depth}层")
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
        
        # 修改逻辑：更倾向于选择包含完整列表的较大容器
        
        # 计算父元素中的列表项数量
        parent_items = count_list_items(parent)
        
        # 检查父元素是否更适合作为容器
        parent_score = calculate_container_score(parent)
        current_score = calculate_container_score(current_container)
        
        print(f"比较得分: 当前={current_score}, 父级={parent_score}")
        print(f"项目数量: 当前={max_items}, 父级={parent_items}")
        
        # 新的升级条件：更宽松，倾向于选择更大的容器
        should_upgrade = False
        
        # 条件1：父级得分明显更高
        if parent_score > current_score + 10:
            should_upgrade = True
            print("父级得分明显更高，升级")
        
        # 条件2：父级得分相近但不是负分，且包含更多项目（但不是太多）
        elif (parent_score >= current_score - 5 and 
              parent_score > -10 and 
              parent_items <= max_items * 2.5):  # 放宽项目数量限制
            should_upgrade = True
            print("父级得分相近且包含更多项目，升级")
        
        # 条件3：当前容器项目太少，父级有合理数量的项目
        elif (max_items < 5 and 
              parent_items >= max_items and 
              parent_items <= 20 and 
              parent_score > -15):
            should_upgrade = True
            print("当前容器项目太少，升级到父级")
        
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
    
    # 最终验证：确保选择的容器包含足够的列表项
    final_items = count_list_items(current_container)
    print(f"最终容器包含 {final_items} 个列表项")
    
    # 如果最终容器项目太少，尝试向上找一层
    if final_items < 5:
        parent = current_container.getparent()
        if parent is not None and parent.tag != 'html':
            parent_items = count_list_items(parent)
            parent_score = calculate_container_score(parent)
            
            # 如果父级有更多项目且得分不是太差，选择父级
            if parent_items > final_items and parent_score > -20:
                print(f"最终调整：选择父级容器 (项目数: {parent_items})")
                current_container = parent
    
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

# def get_robust_xpath(element):
#     """生成更健壮的XPath表达式，处理空格和动态文本"""
#     # 获取基本属性
#     tag = element.tag
#     raw_text = element.text.strip() if element.text else ""
    
#     # 清理文本：移除多余空格和不可见字符
#     cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
    
#     # 获取唯一标识属性
#     attributes = []
#     for attr in ['id', 'class', 'href', 'src', 'name', 'type', 'value']:
#         attr_val = element.attr(attr)
#         if attr_val:
#             # 简化class值（通常有多个类名）
#             if attr == 'class':
#                 # 取第一个有意义的class
#                 first_class = attr_val.split()[0] if attr_val else ""
#                 if first_class and len(first_class) > 2:  # 忽略太短的class
#                     attributes.append(f"contains(@class, '{first_class}')")
#             else:
#                 # 截取部分属性值避免过长
#                 attr_val_short = attr_val[:30] + '...' if len(attr_val) > 30 else attr_val
#                 attributes.append(f"contains(@{attr}, '{attr_val_short}')")
    
#     # 构建XPath选项
#     options = []
    
#     # 选项1：使用清理后的文本 + contains()
#     if cleaned_text:
#         # 取文本的前5个和后5个字符（避免中间变化）
#         text_part = cleaned_text
#         if len(cleaned_text) > 10:
#             text_part = f"{cleaned_text[:5]}...{cleaned_text[-5:]}"
#         options.append(f"contains(text(), '{text_part}')")

    
#     # 组合最终表达式
#     if options:
#         conditions = ' or '.join([f"({opt})" for opt in options])
#         return f"//{tag}[{conditions}]"
#     else:
#         # 最后手段：仅使用标签
#         return f"//{tag}"

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


# 

# 一个页面中，存在k个列表，假定k=3，有三个列表，列表1为导航栏，里面有8个列表项，列表2为侧边栏，里面有5个列表项，列表3是事项列表，里面有7个列表项，
# 此时，我的代码会把列表1作为目标获取，但实际情况应该是列表3才是正确的，这怎么办呢，
# 目前对于目标列表3，可能存在以下特点：里面往往存在时间字符串，并且有些页面中的文字的长度是大于列表1和列表2的。
# 除此之外，对于列表1，也有以下特点：当我们误获取这个列表1的时候，会去处理组装他的xpath，这个xpath里面往往是存在nav三个字母的，
# 在我的观察下，大部分情况中，只要xpath里面包含nav，那就很大可能说明获取失败了，没有获取到列表3，而是获取到了列表1

# 对于js页面，name中名称一定要准确，并且！name要尽量要少一点，比如“法定主动公开内容”，这个就写“法定”即可，这俩字有代表性，不能写“内容”这俩字，没有任何的代表性
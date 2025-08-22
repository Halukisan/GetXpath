def exclude_page_header_footer(page_tree):
    """排除页面级的header和footer区域"""
    # 排除明显的header标签
    headers = page_tree.xpath("//header | //nav | //*[contains(@class, 'header') or contains(@class, 'nav')]")
    for header in headers:
        header.getparent().remove(header)
    
    # 排除明显的footer标签  
    footers = page_tree.xpath("//footer | //*[contains(@class, 'footer') or contains(@class, 'bottom')]")
    for footer in footers:
        footer.getparent().remove(footer)
    
    # 基于内容特征排除首尾部
    header_keywords = ['登录', '注册', '首页', '主页', '无障碍', '政务', '办事', '互动']
    footer_keywords = ['网站说明', '网站标识码', '版权所有', '备案号', 'icp', '公安备案']
    
    all_elements = page_tree.xpath("//*")
    for elem in all_elements:
        text = elem.text_content().lower()
        # 如果包含多个首部关键词，排除
        if sum(1 for kw in header_keywords if kw in text) >= 2:
            if elem.getparent():
                elem.getparent().remove(elem)
        # 如果包含多个尾部关键词，排除
        elif sum(1 for kw in footer_keywords if kw in text) >= 2:
            if elem.getparent():
                elem.getparent().remove(elem)
    
    return page_tree
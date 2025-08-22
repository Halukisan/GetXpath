#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试v3.0算法的简单示例
"""

from lxml import html
from xpathFake import find_list_container, preprocess_html_v3

def test_v3_algorithm():
    """测试v3.0算法"""
    
    # 模拟一个包含header、footer和主内容的HTML
    test_html = """
    <html>
    <body>
        <div class="header">
            <nav>
                <a href="/">首页</a>
                <a href="/service">政务服务</a>
                <a href="/about">无障碍浏览</a>
            </nav>
        </div>
        
        <div class="main-content">
            <div class="news-list">
                <div class="item">
                    <h3>重要通知1</h3>
                    <p>发布时间：2025-01-15</p>
                    <p>这是一条重要的政务信息，内容比较长，包含了详细的说明和要求...</p>
                </div>
                <div class="item">
                    <h3>重要通知2</h3>
                    <p>发布时间：2025-01-14</p>
                    <p>这是另一条重要的政务信息，同样包含了详细的内容和相关要求...</p>
                </div>
                <div class="item">
                    <h3>重要通知3</h3>
                    <p>发布时间：2025-01-13</p>
                    <p>第三条政务信息，内容丰富，包含了多项重要的政策解读...</p>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>版权所有 © 2025 某某政府网站</p>
            <p>网站标识码：1234567890</p>
            <p>主办单位：某某政府办公室</p>
            <p>技术支持：某某科技公司</p>
        </div>
    </body>
    </html>
    """
    
    print("=== 测试v3.0算法 ===")
    
    # 解析HTML
    tree = html.fromstring(test_html)
    
    # 使用v3.0算法查找列表容器
    container = find_list_container(tree)
    
    if container is not None:
        print(f"✅ 成功找到容器: {container.tag}")
        print(f"容器class: {container.get('class', '无')}")
        
        # 检查容器内的列表项
        items = container.xpath(".//div[contains(@class, 'item')]")
        print(f"找到 {len(items)} 个列表项")
        
        for i, item in enumerate(items, 1):
            title = item.xpath(".//h3/text()")
            if title:
                print(f"  项目{i}: {title[0]}")
    else:
        print("❌ 未找到合适的容器")

if __name__ == "__main__":
    test_v3_algorithm()
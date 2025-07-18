# 基于分层搜索策略的网页列表容器定位工具

本项目采用改进的分层搜索策略，从网页中定位包含事项列表的最优父级容器，并生成对应的XPath表达式。

限制项目的重点在于html的获取，有些网页加载的很慢，尽量让代码中selenium等待的时间久一些，如果担心速度太慢，多线程处理的线程数开大一些，资源的消耗并不是非常大。

除此之外，部分网站的防爬机制很严格，目前并未解决。

js部分并未解决。
## 核心算法：分层搜索策略

### 算法流程

1. **初始候选发现**
   ```python
   # 定义多种可能的列表项选择器
   list_selectors = [
       "//li", "//tr", "//article",
       "//div[contains(@class, 'item')]",
       "//div[contains(@class, 'list')]",
       # ...其他选择器
   ]
   ```

2. **容器评分机制**
   ```python
   def calculate_container_score(container):
       score = 0
       # 1. 时间特征检测（目标列表特征）
       time_patterns = [r'\d{4}-\d{2}-\d{2}', r'年', r'月', ...]
       
       # 2. 文本长度检测（目标列表通常有较长文本）
       avg_length = total_length / len(items)
       
       # 3. 导航特征检测（导航栏特征减分）
       if 'nav' in xpath or 'menu' in xpath: 
           score -= 15
       
       # 4. 类名/ID特征分析
       positive_indicators = ['content', 'main', 'list', ...]
       negative_indicators = ['nav', 'menu', 'sidebar', ...]
       return score
   ```

3. **分层优化搜索**
   ```python
   current_container = best_container
   while True:
       parent = current_container.getparent()
       # 计算父元素得分
       parent_score = calculate_container_score(parent)
       current_score = calculate_container_score(current_container)
       
       # 如果父元素得分更高则升级容器
       if parent_score > current_score:
           current_container = parent
       else:
           break
   ```

## 项目结构

```
GetXpath/
├── xpathDsup.py       # 核心处理模块
├── test.yml           # 输入测试文件
├── testoutput.yml     # 结果输出文件
└── README.md          # 项目文档
```

## 输入输出格式

### 输入格式 (test.yml)
```yaml
name: 示例网站
url: https://example.com/list-page
---
name: 另一个示例
url: https://example.com/other-list
```

### 输出格式 (testoutput.yml)
```yaml
name: 示例网站
url: https://example.com/list-page
xpath: "//div[@class='content']/ul[1]"
---
name: 另一个示例
url: https://example.com/other-list
xpath: "//section[@id='main-content']"
```

## 核心功能

### 智能网页获取
- 支持 requests 和 Selenium 双引擎
- 自动重试和后备机制

```python
def get_html_content_Selenium(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            # Selenium获取逻辑
        except:
            return get_html_content(url)  # 后备使用requests
```

### 列表容器定位
- 基于多维度特征评分
- 分层优化搜索策略

### XPath生成
- 优先级策略：ID > 类名 > 属性 > 位置

```python
def generate_xpath(element):
    if element.get('id'):  # 1. 优先使用ID
    elif classes:          # 2. 使用最长类名
    else:                  # 3. 基于位置生成
```


## 算法优势

- **精准识别**：通过时间特征、文本长度等多维度区分目标列表
- **抗干扰能力**：有效过滤导航栏(nav)、菜单(menu)等干扰容器
- **健壮性**：支持多种列表结构（UL/LI、DIV、Table等）
- **自适应优化**：分层搜索确保定位到最合适的容器

## 存在的问题与解决方案

| 问题 | 解决方案 |
|------|----------|
| 部分页面存在多个列表 | 增强时间特征检测权重，增加文本长度分析 |
| 懒加载列表识别困难 | 增加Selenium等待时间，添加滚动加载支持 |
| JS渲染页面支持 | 已集成Selenium Headless浏览器方案 |
| 导航栏误识别 | 添加XPath路径特征检测（nav/menu关键词过滤） |
| 部分站点结构特殊 | 考虑添加站点特定规则扩展机制 |

## 性能优化

### 智能重试机制

```python
for attempt in range(max_retries):
    try:
        # 尝试获取
    except:
        if attempt == max_retries - 1:
            return get_html_content(url)  # 后备方案
```

### 验证机制

```python
def validate_xpath(xpath, html_content):
    results = tree.xpath(xpath)
    # 验证是否找到至少3个列表项
    if len(list_items) >= 3: 
        return True
```

### 批量处理支持

```python
# 支持文件夹批量处理
files = glob.glob(os.path.join(input_folder, "*.yml"))
for input_file in files:
    process_yml_file(input_file, output_file)
```
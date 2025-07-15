
# 基于HNSW索引的网页列表容器定位算法

该项目使用改进的HNSW（Hierarchical Navigable Small World）索引思想，从网页中定位包含事项列表的最优父级容器，并生成对应的XPath表达式。

## 核心算法：分层索引搜索策略

### 算法流程
1. **初始索引构建**
   - 从网页根节点开始，识别所有潜在列表项（`<li>`, `<tr>`, `<article>`, 含"item"类的`<div>`等）
   - 计算每个节点的列表项密度：`节点列表项数 / 节点总元素数`

2. **分层索引搜索**
   ```python
   def hierarchical_search(node, depth=0, max_depth=5):
       if depth >= max_depth:
           return node
       
       # 计算当前节点的列表密度
       current_density = calculate_density(node)
       
       # 获取子节点并计算其密度
       child_nodes = get_child_containers(node)
       child_densities = [calculate_density(c) for c in child_nodes]
       
       # 选择密度最高的子节点
       max_child = child_nodes[child_densities.index(max(child_densities))]
       
       # 递归搜索
       if calculate_density(max_child) > current_density:
           return hierarchical_search(max_child, depth+1, max_depth)
       return node
   ```

3. **终止条件**
   - 达到最大搜索深度（默认5层）
   - 子节点密度低于当前节点密度
   - 当前节点包含的列表项数量显著减少（<3项）

### HNSW索引优化特点
1. **分层导航**
   - 从高密度区域向更高密度区域导航
   - 类似HNSW的"小世界"特性，跳过低密度区域

2. **贪婪搜索策略**
   - 每层选择局部最优解（密度最高子节点）
   - 使用列表项密度而非绝对数量，避免偏向大型容器

3. **自适应深度控制**
   - 动态调整搜索深度
   - 当密度提升<5%时停止搜索

## 项目结构
```
project/
├── processor.py       # 主处理模块
├── hnsw_locator.py    # HNSW定位算法实现
├── test_input.yml     # 输入测试文件
└── output.yml         # 结果输出文件
```

## 输入输出格式
### 输入格式 (`test_input.yml`)
```yaml
name: 示例网站
url: https://example.com/list-page
---
name: 另一个示例
url: https://example.com/other-list
```

### 输出格式 (`output.yml`)
```yaml
name: 示例网站
url: https://example.com/list-page
xpath: "//div[@class='list-container']"
---
name: 另一个示例
url: https://example.com/other-list
xpath: "//ul[@id='item-list']"
```

## 性能优化
1. **密度缓存**
   - 缓存已计算节点的密度值
   - 减少重复计算

2. **提前终止**
   ```python
   if current_density > 0.8:  # 高密度节点直接返回
       return node
   ```

3. **并行处理**
   ```python
   from concurrent.futures import ThreadPoolExecutor
   
   with ThreadPoolExecutor() as executor:
       results = executor.map(process_entry, entries)
   ```

## 使用示例
```python
from hnsw_locator import locate_list_container

html_content = fetch_url(url)
container = locate_list_container(html_content)
xpath = generate_xpath(container)
print(f"列表容器XPath: {xpath}")
```

## 算法优势
1. **精确性**：定位到最近的列表容器而非整个页面
2. **鲁棒性**：适应多种网页结构（UL/LI、DIV、Table等）
3. **高效性**：平均搜索深度<4层，时间复杂度O(log N)


## 存在的问题

1. 部分页面存在两个列表的情况，页面左侧为目标事项列表，右侧为干扰列表，但情况是，左侧事项列表是懒加载，需要用户下滑后才会显示，但此时右侧干扰列表的密度大于左侧事项列表的密度，导致程序识别错误。
2. js渲染的页面，无法识别

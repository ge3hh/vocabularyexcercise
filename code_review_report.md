# 词汇练习项目代码审核报告

**审核日期**: 2026-03-24
**项目地址**: https://github.com/ge3hh/vocabularyexcercise.git
**审核范围**: 完整代码库

---

## 项目概述

这是一个英语词汇练习工具，包含两个版本：
- **Web 版** (`web_app.py`)：基于 Python 标准库 `http.server`，零依赖
- **桌面版** (`VocabularyExcecise2.py`)：基于 Tkinter

**功能特性**：
- 艾宾浩斯式复习间隔算法
- 错题本功能
- 多词库支持（高中/四级/六级）
- 统计面板
- CSV 导入导出

---

## 发现的问题

### 🔴 高优先级（安全/稳定性）

#### 1. SQL 注入隐患

**位置**: `vocabulary_pool.py` 多处

**问题描述**: 使用 f-string 拼接 SQL 语句，表名直接插入 SQL 中：

```python
cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
```

**风险**: 虽然当前表名来自硬编码字典，但如果未来扩展或代码被误用，可能导致 SQL 注入。

**建议修复**: 添加表名白名单验证：

```python
def validate_table_name(table_name):
    if table_name not in LIBRARY_TABLES.values():
        raise ValueError(f"Invalid table name: {table_name}")
```

---

#### 2. 会话内存泄漏

**位置**: `web_app.py` 第 35 行

**问题描述**: `SESSIONS = {}` 全局字典无限增长，没有过期清理机制。每个访问者都会创建新会话，长时间运行会导致内存耗尽。

**风险**: 服务稳定性风险，可能被恶意攻击者利用进行 DoS 攻击。

**建议修复**: 添加会话过期时间：

```python
from datetime import datetime, timedelta

SESSIONS = {}
SESSION_TIMEOUT = timedelta(hours=24)

def cleanup_expired_sessions():
    now = datetime.now()
    expired = [sid for sid, data in SESSIONS.items()
               if now - data.get('created_at', now) > SESSION_TIMEOUT]
    for sid in expired:
        del SESSIONS[sid]
```

---

#### 3. 文件上传安全隐患

**位置**: `web_app.py` 第 534-545 行

**问题描述**:
1. 使用固定临时文件名 `_upload_temp.csv`，并发请求会相互覆盖
2. 临时文件写入项目目录，存在路径遍历风险
3. 没有文件大小限制

**风险**:
- 并发上传数据丢失或混淆
- 恶意大文件上传可导致磁盘耗尽

**建议修复**: 使用 `tempfile` 模块：

```python
import tempfile
import os

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def handle_import_upload(session_state, fields):
    upload = fields.get("csv_file")
    if not upload or not upload.get("content"):
        add_flash(session_state, "error", "请选择要导入的 CSV 文件。")
        self.redirect("/#library-management")
        return

    # 文件大小检查
    if len(upload["content"]) > MAX_FILE_SIZE:
        add_flash(session_state, "error", "文件过大，请限制在 10MB 以内。")
        self.redirect("/#library-management")
        return

    # 使用临时文件
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as tmp:
        tmp.write(upload["content"])
        temp_path = tmp.name

    try:
        imported_count = import_new_words(temp_path, get_table_name(session_state))
        add_flash(session_state, "success", f"成功导入 {imported_count} 个单词。")
    except Exception as exc:
        add_flash(session_state, "error", f"导入词库失败：{exc}")
    finally:
        os.unlink(temp_path)

    self.redirect("/#library-management")
```

---

### 🟡 中优先级（健壮性）

#### 4. 输入验证不完善

**位置**: `vocabulary_pool.py` 第 128-157 行 (`import_new_words`)

**问题描述**: CSV 导入时缺少对列名的验证，如果 CSV 格式不正确会导致数据错误或异常。

**建议修复**: 验证必要列名：

```python
def import_new_words(filename, table_name):
    csv_rows = read_csv_rows(filename)
    if not csv_rows:
        return 0

    # 验证列名
    required_columns = {'english'}
    first_row = csv_rows[0]
    if not required_columns.issubset(first_row.keys()):
        missing = required_columns - first_row.keys()
        raise ValueError(f"CSV 文件缺少必要列: {missing}")

    # ... 继续处理
```

---

#### 5. 资源管理不完善

**位置**: 多处文件操作

**问题描述**: 部分文件操作缺少 `try-finally` 确保资源释放。

**当前代码** (`vocabulary_pool.py` 第 346-361 行):

```python
with open(file_path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
    # ... 写入数据
```

虽然使用了 `with` 语句，但某些场景下异常处理不够完善。

---

### 🟢 低优先级（代码质量）

#### 6. 拼写错误

**位置**: 文件名 `VocabularyExcecise2.py`

**问题**: `Excecise` 应为 `Exercise`

**建议**: 重命名文件，并更新所有引用。

---

#### 7. 代码重复

**问题描述**: 桌面版和 Web 版有大量重复逻辑：
- `BUILTIN_LIBRARY_FILES` 定义重复
- 业务逻辑在两个版本中都存在

**建议**: 将共享逻辑完全抽取到 `vocabulary_pool.py`

---

#### 8. 缺少日志记录

**问题描述**: 整个项目没有使用 `logging` 模块，难以排查问题。

**建议**: 添加基础日志配置：

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
```

---

## 优先级总结

| 优先级 | 问题 | 影响 | 建议处理时间 |
|--------|------|------|-------------|
| 🔴 高 | SQL 注入风险 | 数据安全 | 立即 |
| 🔴 高 | 会话内存泄漏 | 稳定性 | 立即 |
| 🔴 高 | 文件上传安全 | 系统安全 | 立即 |
| 🟡 中 | 输入验证缺失 | 数据完整性 | 近期 |
| 🟡 中 | 资源管理 | 可靠性 | 近期 |
| 🟢 低 | 拼写错误 | 可读性 | 可选 |
| 🟢 低 | 代码重复 | 维护成本 | 可选 |
| 🟢 低 | 缺少日志 | 可调试性 | 可选 |

---

## 架构建议

当前直接使用 `http.server` 虽然零依赖，但存在以下局限：
1. 模板、路由、请求处理混杂在一个文件
2. 缺少中间件支持
3. 生产环境安全性不足

**建议**: 如果项目规模扩大，考虑迁移到轻量级框架如 Flask 或 FastAPI。

---

## 正向评价

1. **零依赖设计**: Web 版仅使用 Python 标准库，部署简单
2. **功能完整**: 艾宾浩斯算法、错题本、统计功能齐全
3. **代码结构清晰**: `vocabulary_pool.py` 分离了数据层逻辑
4. **双版本支持**: 同时提供 Web 和桌面版本，适配不同场景
5. **中文注释充分**: 代码可读性好

---

*报告生成时间: 2026-03-24*

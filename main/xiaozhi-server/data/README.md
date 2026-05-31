# Poem Database (古诗库)

> 服务端笔顺查询功能用的本地古诗数据集。
>
> 完整设计文档见 [`firmware/docs/poem-database.md`](../../../../../firmware/docs/poem-database.md)。

## 文件清单

| 文件 | 用途 | 是否纳入 git |
|------|------|------------|
| `poems_curated.json` | 主数据集（手工维护）| ✅ |
| `poem_index.json` | 倒排索引（脚本生成）| ✅ |
| `README.md` | 本文 | ✅ |

## 维护命令

### 添加 / 修改诗

直接编辑 `poems_curated.json`，按已有格式追加：

```json
{
  "title": "诗名",
  "author": "作者",
  "source": "primary75 | junior50 | tang300 | song-ci | other | manual-fix-X",
  "couplets": [
    "上句，下句",
    "上句，下句"
  ]
}
```

每个 couplet 必须用中文逗号 `，` 分隔上下两句。

### 重建索引

```bash
cd server/src/main/xiaozhi-server
python scripts/build_poem_index.py
```

### 部署后

`lookup_stroke.py` 模块**启动时**载入 `poem_index.json`，所以改完数据集后**必须重启 docker 容器**才生效：

```bash
docker restart xiaozhi-esp32-server
```

## 字段约定

### `source` 标签

| 标签 | 含义 |
|------|------|
| `primary75` | 教育部 2017 新课标小学必背古诗 75 首 |
| `junior50` | 初中必背古诗（部编版语文教材）|
| `tang300` | 唐诗三百首中除上述以外、最著名的 |
| `song-ci` | 著名宋词 |
| `other` | 古诗十九首、汉魏诗、岳飞、文天祥、毛泽东等 |
| `manual-fix-X` | 因 `[POEM-EMPTY]` 日志反馈、为字 X 手工补的（保留追溯）|

### Couplet 格式约束

**✓ 合格**（两句一对，中间用中文逗号分隔）：
- `"床前明月光，疑是地上霜"`
- `"春眠不觉晓，处处闻啼鸟"`

**✗ 不合格**：
- `"床前明月光"` — 单句，没有韵律对仗
- `"床前明月光,疑是地上霜"` — 用了英文逗号（脚本能处理但不规范）
- `"床前明月光，疑是地上霜。举头望明月，低头思故乡"` — 4 句一组，应拆成 2 个 couplet

`build_poem_index.py` 会跳过不合格的 couplet 并打 warning。

## 长期维护策略

数据集是活数据，根据 `[POEM-EMPTY]` 日志反馈滚动扩充。详见 `firmware/docs/poem-database.md` 第七节《扩充流程》。

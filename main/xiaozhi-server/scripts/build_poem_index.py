"""
build_poem_index.py — 把 data/poems_curated.json 转成倒排索引 data/poem_index.json

用法（在 server/src/main/xiaozhi-server/ 下运行）：
    python scripts/build_poem_index.py

详见 firmware/docs/poem-database.md。
"""
import io
import json
import os
import sys
from collections import defaultdict

# Windows 下 PowerShell GBK codepage 默认不能输出非 GBK 字符，
# 强制把 stdout/stderr 改成 utf-8（用 utf-8 替换 BOM 不影响 redirect）
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def is_cjk(ch: str) -> bool:
    """判断是否是汉字（CJK Unified Ideographs 范围 + 扩展 A）"""
    cp = ord(ch)
    return (
        (0x4E00 <= cp <= 0x9FFF)       # CJK 基本
        or (0x3400 <= cp <= 0x4DBF)    # 扩展 A
        or (0xF900 <= cp <= 0xFAFF)    # 兼容
    )


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.normpath(os.path.join(here, '..', 'data'))
    src_path = os.path.join(data_dir, 'poems_curated.json')
    out_path = os.path.join(data_dir, 'poem_index.json')

    if not os.path.exists(src_path):
        print(f"[ERROR] 找不到 {src_path}", file=sys.stderr)
        sys.exit(1)

    with open(src_path, encoding='utf-8') as f:
        poems = json.load(f)

    # 倒排索引：字 → set of couplet（用 set 自动去重）
    index = defaultdict(set)
    couplet_count = 0
    poem_count = 0
    skipped_couplets = 0

    for poem in poems:
        title = poem.get('title', '?')
        couplets = poem.get('couplets', [])
        if not couplets:
            continue
        poem_count += 1
        for couplet in couplets:
            couplet = couplet.strip()
            if not couplet:
                continue
            # 健壮性校验：couplet 必须含至少一个分隔符（，；,）= 两句一对
            if not any(c in couplet for c in '，,；;'):
                print(
                    f"[WARN] 《{title}》couplet 不像两句一对（缺分隔符）: {couplet}",
                    file=sys.stderr,
                )
                skipped_couplets += 1
                continue
            couplet_count += 1
            for ch in couplet:
                if is_cjk(ch):
                    index[ch].add(couplet)

    # set → list（JSON 不支持 set），同时按字符串排序保证输出稳定
    index_list = {ch: sorted(list(couplets)) for ch, couplets in index.items()}

    # 按字 unicode 排序输出，方便人眼比对
    index_list = dict(sorted(index_list.items(), key=lambda kv: ord(kv[0])))

    # 写盘
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(index_list, f, ensure_ascii=False, indent=None, separators=(',', ':'))

    # 统计
    total_pairs = sum(len(v) for v in index_list.values())
    out_size_kb = os.path.getsize(out_path) / 1024

    print(f"[build_poem_index] 输入: {poem_count} 首诗, {couplet_count} 个 couplet")
    if skipped_couplets:
        print(f"[build_poem_index] [WARN] 跳过 {skipped_couplets} 个不合规 couplet（缺分隔符）")
    print(f"[build_poem_index] 索引覆盖: {len(index_list)} 个不同汉字")
    print(f"[build_poem_index] 总条目: {total_pairs} (字→诗) 对")
    print(f"[build_poem_index] 输出: {out_path} ({out_size_kb:.1f} KB)")

    # 抽几个常见字看看（健壮性 sanity check）
    sample_chars = ['月', '春', '雪', '山', '水', '友', '病', '孙', '龙', '龟', '鹅']
    print(f"\n[build_poem_index] 抽查样本：")
    for ch in sample_chars:
        n = len(index_list.get(ch, []))
        flag = '✓' if n > 0 else '✗ MISSING'
        print(f"  {ch}: {n} 首 {flag}")


if __name__ == '__main__':
    main()

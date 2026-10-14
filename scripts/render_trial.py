#!/usr/bin/env python3
"""Render completed trial artifacts into one offline, escaped HTML reader."""
import argparse
import html
import json
from pathlib import Path
from urllib.parse import urlsplit


def esc(value):
    return html.escape(str(value), quote=True)


def render(directory):
    state_path = directory / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    cards = []
    quoted_words = {}
    labels = {'biology': '生物', 'finance': '金融', 'industry': '产业', 'cross-disciplinary': '交叉'}
    kinds = {'fact': '事实', 'inference': '推断', 'unknown': '未知'}
    for path in sorted((directory / 'cards').glob('*.json')):
        item = json.loads(path.read_text(encoding='utf-8'))
        card, question = item['card'], item['question']
        topic = question.get('domain', question.get('topic', '交叉'))
        topic = labels.get(topic, topic)
        def claim(c):
            refs = ''.join(' <a href="#' + esc(card['question_id'] + '-' + sid) + '">[' + str(next((i + 1 for i, s in enumerate(item['sources']) if s['id'] == sid), '?')) + ']</a>' for sid in c['source_ids'])
            return '<span class="kind">' + esc(kinds.get(c['kind'], c['kind'])) + '</span>' + esc(c['text']) + '<sup>' + refs + '</sup>'
        sources = []
        for source_number, source in enumerate(item['sources'], 1):
            url = source['url']
            if urlsplit(url).scheme != 'https':
                continue
            published = source.get('published_at')
            if not published or published == 'unknown':
                published = '未注明'
            sources.append('<li id="' + esc(card['question_id'] + '-' + source['id']) + '">[' + str(source_number) + '] <a target="_blank" rel="noopener noreferrer" href="' + esc(url) + '">' + esc(source['title']) + '</a><small>发表/更新：' + esc(published) + ' · 读取：' + esc(source.get('accessed_at', source.get('retrieved_at', ''))) + '</small></li>')
        evidence_parts = []
        for entry in card['evidence']:
            sid = entry['source_id']
            remaining = max(0, 25 - quoted_words.get(sid, 0))
            words = entry['quote'].split()
            selected = words[:remaining]
            quoted_words[sid] = quoted_words.get(sid, 0) + len(selected)
            snippet = ' '.join(selected) + (' …' if len(words) > len(selected) else '') if selected else '更多证据请查看原始资料。'
            targets = ['结论' if t == 'answer' else '解释 ' + str(int(t.split('.')[-1]) + 1) for t in entry['supports']]
            evidence_parts.append('<blockquote>' + esc(snippet) + '<small>支持：' + esc('、'.join(targets)) + ' · <a href="#' + esc(card['question_id'] + '-' + sid) + '">对应原始资料</a></small></blockquote>')
        evidence = ''.join(evidence_parts)
        cards.append('<article data-topic="' + esc(topic) + '" data-id="' + esc(card['question_id']) + '"><div class="eyebrow">' + esc(topic) + '<button class="read" type="button" aria-pressed="false">标记已读</button></div><h2>' + esc(card['title']) + '</h2><p class="question">' + esc(question.get('question', question.get('text', ''))) + '</p><p class="answer">' + claim(card['answer']) + '</p><ol class="reasoning">' + ''.join('<li>' + claim(c) + '</li>' for c in card['reasoning']) + '</ol><div class="boundary"><b>何时不成立</b><p>' + esc('；'.join(card['limitations'])) + '</p><b>接下来观察</b><p>' + esc('；'.join(card['indicators'])) + '</p></div><p class="uncertain">尚不确定：' + esc(card['uncertainty']) + '</p><details><summary>查看证据与原始资料</summary>' + evidence + '<ul class="sources">' + ''.join(sources) + '</ul></details></article>')
    count = len(cards)
    body = ''.join(cards) or '<div class="empty">本轮尚无通过检查的成品。这里不会用示例回答填充。</div>'
    status = {'running': '生成中', 'completed': '已结束', 'stopped': '已停止', 'dry_run': '仅预演'}.get(state.get('status'), '试运行记录')
    page = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ask · 试读</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f2ec;color:#222b29;font:17px/1.8 system-ui,"Microsoft YaHei",sans-serif}header,main,footer{max-width:900px;margin:auto;padding:34px 24px}header{padding-bottom:16px}.brand{font:600 14px/1.4 system-ui;letter-spacing:3px;color:#547366}h1{font-size:clamp(30px,5vw,46px);line-height:1.25;margin:15px 0}header p{color:#59665f;margin:8px 0}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0 4px}input,select,button{font:inherit;border:1px solid #c8d0c8;border-radius:7px;background:#fff;padding:8px 12px;color:inherit}input{flex:1;min-width:180px}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #558a75;outline-offset:3px}main{padding-top:8px}article{background:#fff;border:1px solid #dddcd3;border-radius:12px;padding:28px 34px;margin:18px 0 30px;box-shadow:0 5px 18px #27392d05}.eyebrow{font-size:13px;letter-spacing:1px;color:#47705e;display:flex;justify-content:space-between;align-items:center}.read{font-size:12px;padding:4px 9px}article.is-read .read{background:#e5eee7}.is-read{border-left:4px solid #7b9b86}h2{font-size:25px;line-height:1.5;margin:16px 0 8px}.question{font-size:14px;color:#6c716b}.answer{font-size:20px;font-weight:600;margin:18px 0}.kind{font-size:11px;font-weight:400;padding:2px 5px;margin-right:8px;color:#476556;background:#edf2ed;border-radius:4px;white-space:nowrap;vertical-align:middle}.reasoning{padding-left:25px}.reasoning li{padding-left:6px;margin:12px 0}.boundary{background:#f7f7f2;border-left:3px solid #bacab9;padding:14px 18px;font-size:15px}.boundary p{margin:3px 0 12px}.boundary p:last-child{margin-bottom:0}.boundary b{font-size:12px;color:#5d7465}.uncertain{font-size:13px;color:#74766d}details{font-size:14px;border-top:1px solid #eeeee6;padding-top:12px}summary{cursor:pointer;color:#456855}blockquote{border-left:2px solid #d1dcca;margin:16px 0;padding:2px 14px;color:#666;font-size:13px}small{display:block;font-size:11px;color:#82867f}a{color:#355f50;overflow-wrap:anywhere}.sources{padding-left:20px}.sources li{margin:12px 0}.empty{padding:32px;color:#696f67}footer{font-size:12px;color:#74796e;padding-top:0}[hidden]{display:none!important}@media(max-width:560px){header,main,footer{padding-left:16px;padding-right:16px}article{padding:20px}h2{font-size:22px}.answer{font-size:18px}}@media print{body{background:white}article{break-inside:avoid;box-shadow:none}button,.toolbar{display:none}details{display:block}}
</style></head><body><header><div class="brand">ASK / 试读</div><h1>把等待，变成可读的积累。</h1><p>生物 · 金融 · 产业　｜　COUNT 篇已完成　｜　STATUS</p><div class="toolbar"><input id="search" aria-label="搜索内容" placeholder="搜索问题、概念或结论"><select id="topic" aria-label="筛选领域"><option value="">全部领域</option><option>生物</option><option>金融</option><option>产业</option><option>交叉</option></select></div><small id="visible" aria-live="polite"></small></header><main>CARDS</main><footer>内容来自本轮实际完成的模型调用；引用已检查能在输入资料中找到，事实正确性仍需复核。已读状态仅保存在当前浏览器，打开页面不会调用模型。<br>FINISHED</footer><script>
const cards=[...document.querySelectorAll('article')];let saved={};try{saved=JSON.parse(localStorage.getItem('ask-read-v1')||'{}')}catch(e){}for(const c of cards){const b=c.querySelector('button');function update(){const read=Boolean(saved[c.dataset.id]);c.classList.toggle('is-read',read);b.textContent=read?'已读 · 撤销':'标记已读';b.setAttribute('aria-pressed',String(read))}update();b.addEventListener('click',()=>{saved[c.dataset.id]=!saved[c.dataset.id];try{localStorage.setItem('ask-read-v1',JSON.stringify(saved))}catch(e){}update()})}function filter(){const q=document.getElementById('search').value.trim().toLowerCase(),topic=document.getElementById('topic').value;let n=0;for(const c of cards){c.hidden=Boolean((topic&&c.dataset.topic!==topic)||(q&&!c.textContent.toLowerCase().includes(q)));if(!c.hidden)n++}document.getElementById('visible').textContent='显示 '+n+' 篇'}document.getElementById('search').addEventListener('input',filter);document.getElementById('topic').addEventListener('change',filter);filter();
</script></body></html>'''
    return page.replace('COUNT', str(count)).replace('STATUS', esc(status)).replace('FINISHED', esc(state.get('finished_at', state.get('updated_at', '')))).replace('CARDS', body).replace('何时不成立', '适用边界')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.directory / 'index.html'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.directory), encoding='utf-8')
    print(json.dumps({'reader': str(output)}, ensure_ascii=False))

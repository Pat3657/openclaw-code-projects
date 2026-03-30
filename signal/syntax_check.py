html = open('/workspace/signal/index.html').read()
start = html.rfind('<script>')
end   = html.rfind('</script>')
js = html[start+8:end]

depth = 0; pdepth = 0; in_str = None; i = 0; issues = []
bs = chr(92)
while i < len(js):
    c = js[i]
    if in_str:
        if c == bs: i+=2; continue
        if c == in_str: in_str = None
    elif c in ('"', "'", '`'): in_str = c
    elif c == '{': depth += 1
    elif c == '}':
        depth -= 1
        if depth < 0: issues.append(i); depth = 0
    elif c == '(': pdepth += 1
    elif c == ')': pdepth -= 1
    i += 1

print(f'Brace depth: {depth}, Paren depth: {pdepth}, Extra closes: {len(issues)}')
if issues:
    for pos in issues[:3]:
        print(f'  Extra close at {pos}: ...{repr(js[max(0,pos-50):pos+50])}...')

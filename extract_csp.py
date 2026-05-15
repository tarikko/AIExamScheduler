import json

d = json.load(open('c:/Users/Azur Computer/OneDrive/Documents/aiproj/AIExamScheduler/notebook/algorithms.ipynb', encoding='utf-8'))
for cell in d['cells']:
    source = ''.join(cell.get('source', []))
    if 'class CSP' in source:
        with open('c:/Users/Azur Computer/OneDrive/Documents/aiproj/AIExamScheduler/scratch_csp.py', 'w', encoding='utf-8') as f:
            f.write(source)

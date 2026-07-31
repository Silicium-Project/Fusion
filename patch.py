import os
path = r'C:\Users\luisf\AppData\Roaming\SiliciumNode\runtime\Network\tools\network_node.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('parser.add_argument("--roles"', 'parser.add_argument("--pull-tasks-enable", action="store_true")\n    parser.add_argument("--pull-tasks-interval-s", type=int, default=1)\n    parser.add_argument("--roles"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

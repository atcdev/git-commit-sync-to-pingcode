# -*- coding: utf-8 -*-

# 导入必要的模块和库
import sys
import os
import urllib
import urllib.parse
import urllib.request
import json
import tempfile
import re

client_id = ''
client_secret = ''
rest_api_root = 'https://open.pingcode.com'

# 读取并解析 HTTP 响应数据为 JSON 格式
def resolve_res_data(res):
        res_data = res.read().decode('UTF8')
        return json.loads(res_data)

# 从字符串中解析出所有符合格式的 issue 标识符
def resolve_identifiers(str):
        matchs = re.findall('#[a-zA-Z0-9]+-[0-9]+', str, re.M)
        identifiers = []
        for match in matchs:
            identifiers.append(match[1:])
        return identifiers

# 从临时目录中加载缓存数据
def get_cache():
        cache_file = os.path.join(tempfile.gettempdir(), 'pc_cache')
        if os.path.exists(cache_file):
            file = open(cache_file, 'r')
            cache = file.read()
            file.close()
            return json.loads(cache)
        else:
            return

# 通过客户端认证方式获取访问令牌
def get_token():
        uri = rest_api_root + '/v1/auth/token?grant_type=client_credentials&client_id=' + client_id + '&&client_secret=' + client_secret
        res_data = resolve_res_data(urllib.request.urlopen(uri))
        if res_data['access_token']:
            return res_data['access_token']
        else:
            raise Exception("Invalid client_id or client_secret")

# 根据提供的token验证服务API是否响应
def ping(token):
        uri = rest_api_root + '/v1/auth/ping?access_token=' + token
        res_data = resolve_res_data(urllib.request.urlopen(uri))
        if res_data['data']:
            return True
        else:
            return False

# 获取资源信息，根据token、路径、属性和值获取资源ID
def get_resource(token, path, prop, value):
        method = "GET"
        uri = rest_api_root + path + "?" + prop + "=" + urllib.parse.quote(value)
        headers = {'authorization': 'Bearer ' + token}
        req = urllib.request.Request(uri, headers = headers, method = method)
        res_data = resolve_res_data(urllib.request.urlopen(req))
        if res_data['values'] and len(res_data['values']) > 0 and res_data['values'][0][prop] == value:
            return res_data['values'][0]["id"]
        else:
            return

# 创建资源，根据token、路径、请求体和是否抛出异常来创建资源并返回ID
def create_resource(token, path, body, throwError):
        method = 'POST'
        uri = rest_api_root + path
        headers = {'Content-Type': 'application/json', 'authorization': 'Bearer ' + token}
        data = json.dumps(body).encode(encoding='UTF8')
        req = urllib.request.Request(uri, data = data, headers = headers, method = method)
        try:
            res_data = resolve_res_data(urllib.request.urlopen(req))
            if res_data and res_data['id']:
                return res_data['id']
            else:
                raise Exception('Create resource failed: ' + path)
        except:
            if throwError:
                value = sys.exc_info()
                raise value[1]

# 根据token、路径、属性和值，获取或创建资源并返回ID
def get_or_create_resource(token, path, prop, value, body):
        id = get_resource(token, path, prop, value)
        if not id:
            id = create_resource(token, path, body, True)
        return id

# 获取或创建产品ID
def get_product_id(token):
        path = '/v1/scm/products'
        body = {'name': 'Git', 'type': 'git'}
        return get_or_create_resource(token, path, 'name', 'Git', body)

# 获取或创建仓库ID
def get_repo_id(token, product_id, name):
        path = '/v1/scm/products/' + product_id + '/repositories'
        body = {'name': name, 'full_name': name}
        return get_or_create_resource(token, path, 'full_name', name, body)

# 获取或创建分支ID
def get_branch_id(token, product_id, repo_id, name):
        path = '/v1/scm/products/' + product_id + '/repositories/' + repo_id + '/branches'
        body = {'name': name, 'sender_name': 'system', 'work_item_identifiers': resolve_identifiers(name)}
        return get_or_create_resource(token, path, 'name', name, body)

# 保存缓存信息到文件
def save_cache(cache):
        cache_file = os.path.join(tempfile.gettempdir(), 'pc_cache')
        file = open(cache_file, 'w')
        file.write(json.dumps(cache))
        file.close()

# 获取提交记录
def get_commits():
        if sys.argv[4] == '0000000000000000000000000000000000000000':
            return []
        else:
            cmd = 'git log --pretty=format:"%H+++++%T+++++%cn+++++%at+++++%s" ' + sys.argv[4] + '..' + sys.argv[5]
            output = os.popen(cmd).read()
            infos = output.split('\n')
            commits = []
            for info in infos:
                commit = info.split('+++++')
                commits.append({'sha': commit[0], 'tree_id': commit[1], 'committer_name': commit[2], 'committed_at': int(commit[3]), 'message': commit[4], 'work_item_identifiers': resolve_identifiers(commit[4]), 'files_added': [], 'files_removed': [], 'files_modified': []})
            return commits

# 同步提交记录到远程
def forward_commits(token, product_id, repo_id, branch_id, cache):
        users = cache["users"]
        commits = get_commits()
        for commit in commits:
            create_resource(token, '/v1/scm/commits', commit, False)
            create_resource(token, '/v1/scm/products/' + product_id + '/repositories/' + repo_id + '/refs', {'sha': commit["sha"], 'meta_type': 'branch', 'meta_id': branch_id}, False)
            if not hasattr(users, commit["committer_name"]):
                create_resource(token, '/v1/scm/products/' + product_id +'/users', { 'name': commit["committer_name"]}, False)
                users[commit["committer_name"]] = True
        cache["users"] = users

# 获取分支名称
def get_branch_name():
        refs = sys.argv[3].split('/')
        if refs[0] == 'refs' and refs[1] == 'heads':
            return '/'.join(refs[2:])
        else:
            return

# 主函数，处理逻辑核心
def main():
    repo_name = sys.argv[1]
    branch_name = get_branch_name()
    if branch_name:
        cache = get_cache()
        if cache:
            token = cache['token']
            if not ping(token):
                cache['token'] = token = get_token()
            product_id = cache['product_id']
            if not hasattr(cache['repos'], repo_name):
                cache['repos'][repo_name] = { 'id': get_repo_id(token, product_id, repo_name), 'refs': {} }
            repo_id = cache['repos'][repo_name]["id"]
            if not hasattr(cache['repos'][repo_name]['refs'], branch_name):
                cache['repos'][repo_name]['refs'][branch_name] = { 'id': get_branch_id(token, product_id, repo_id, branch_name) }
            branch_id = cache['repos'][repo_name]['refs'][branch_name]["id"]
            forward_commits(token, product_id, repo_id, branch_id, cache)
            save_cache(cache)
        else:
            token = get_token()
            product_id = get_product_id(token)
            repo_id = get_repo_id(token, product_id, repo_name)
            branch_id = get_branch_id(token, product_id, repo_id, branch_name)
            cache_refs = { branch_name: { 'id': branch_id } }
            cache_repos = { repo_name: { 'id': repo_id, 'refs': cache_refs } } 
            cache = {'token': token, 'product_id': product_id, 'repos': cache_repos, 'users': {}}
            forward_commits(token, product_id, repo_id, branch_id, cache)
            save_cache(cache)

# 设置工作目录为脚本执行目录
os.chdir(sys.argv[2])
# 执行主函数
main()
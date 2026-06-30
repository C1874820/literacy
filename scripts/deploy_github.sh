#!/bin/bash
# GitHub Pages 部署脚本
# 用法: ./scripts/deploy_github.sh <github_username> [repo_name]
# 需要先申请 GitHub Personal Access Token (classic, repo scope)
# 申请地址: https://github.com/settings/tokens

set -e

if [ $# -lt 1 ]; then
    echo "用法: $0 <github_username> [repo_name]"
    echo "示例: $0 yourname rex-literacy"
    exit 1
fi

USERNAME=$1
REPO=${2:-rex-literacy}
TOKEN="${GITHUB_TOKEN}"

if [ -z "$TOKEN" ]; then
    echo "请输入 GitHub Personal Access Token（输入后不会显示）:"
    read -s TOKEN
    echo ""
fi

echo "=== 创建 GitHub 仓库: $USERNAME/$REPO ==="
curl -s -H "Authorization: token $TOKEN" \
     -H "Content-Type: application/json" \
     -X POST "https://api.github.com/user/repos" \
     -d "{\"name\":\"$REPO\",\"description\":\"Rex 识字进度\",\"auto_init\":true,\"homepage\":\"https://$USERNAME.github.io/$REPO/progress/\"}" \
     | grep -q '"name"'

echo "=== 推送代码 ==="
cd "$(dirname "$0")/.."
git remote add origin "https://$USERNAME:$TOKEN@github.com/$USERNAME/$REPO.git" 2>/dev/null || \
    git remote set-url origin "https://$USERNAME:$TOKEN@github.com/$USERNAME/$REPO.git"

# 推送并启用 GitHub Pages
git push -u origin master

echo "=== 启用 GitHub Pages ==="
curl -s -H "Authorization: token $TOKEN" \
     -H "Content-Type: application/json" \
     -X POST "https://api.github.com/repos/$USERNAME/$REPO/pages" \
     -d "{\"source\":{\"branch\":\"master\",\"path\":\"/\"}}" \
     > /dev/null 2>&1 || true

echo ""
echo "✅ 部署完成！访问地址："
echo "   https://$USERNAME.github.io/$REPO/progress/"
echo ""
echo "注：GitHub Pages 启用后可能需要 1-2 分钟生效"
echo "以后更新只需在仓库目录执行: git push"

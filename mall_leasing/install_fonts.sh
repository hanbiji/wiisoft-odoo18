#!/bin/bash
# Odoo PDF中文字体安装脚本

echo "========================================"
echo "Odoo PDF中文字体安装脚本"
echo "========================================"

# 检测操作系统
if [ -f /etc/debian_version ]; then
    echo "检测到 Debian/Ubuntu 系统"
    echo "正在安装中文字体..."
    sudo apt-get update
    sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk fonts-arphic-ukai fonts-arphic-uming
    
elif [ -f /etc/redhat-release ]; then
    echo "检测到 CentOS/RHEL 系统"
    echo "正在安装中文字体..."
    sudo yum install -y wqy-zenhei-fonts wqy-microhei-fonts google-noto-sans-cjk-fonts
    
else
    echo "未识别的操作系统，请手动安装中文字体"
    exit 1
fi

# 更新字体缓存
echo "更新字体缓存..."
sudo fc-cache -fv

# 验证安装
echo ""
echo "========================================"
echo "已安装的中文字体："
echo "========================================"
fc-list :lang=zh | head -10

echo ""
echo "========================================"
echo "安装完成！"
echo "========================================"
echo ""
echo "下一步操作："
echo "1. 重启 Odoo 服务: sudo systemctl restart odoo"
echo "2. 升级模块: odoo-bin -c /path/to/odoo.conf -u mall_leasing -d your_database"
echo "3. 测试打印合同PDF"
echo ""


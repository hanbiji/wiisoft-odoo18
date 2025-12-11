#!/bin/bash
# Microsoft YaHei 字体安装脚本

echo "======================================"
echo "Microsoft YaHei 字体安装向导"
echo "======================================"
echo ""
echo "注意：Microsoft YaHei 是商业字体，需要有合法授权才能使用。"
echo ""
echo "安装步骤："
echo "1. 从 Windows 系统复制字体文件到此服务器"
echo "   Windows 字体路径：C:\\Windows\\Fonts\\"
echo "   需要复制的文件："
echo "   - msyh.ttc（微软雅黑 常规）"
echo "   - msyhbd.ttc（微软雅黑 粗体）"
echo "   - msyhl.ttc（微软雅黑 细体，可选）"
echo ""
echo "2. 将字体文件上传到服务器的 /tmp 目录"
echo ""
echo "3. 运行此脚本进行安装"
echo ""

# 检查字体文件是否存在
FONT_DIR="/tmp"
FONTS_FOUND=0

if [ -f "$FONT_DIR/msyh.ttc" ]; then
    echo "✓ 找到 msyh.ttc"
    FONTS_FOUND=1
fi

if [ -f "$FONT_DIR/msyhbd.ttc" ]; then
    echo "✓ 找到 msyhbd.ttc"
    FONTS_FOUND=1
fi

if [ $FONTS_FOUND -eq 0 ]; then
    echo ""
    echo "❌ 错误：未在 /tmp 目录找到字体文件"
    echo ""
    echo "请先将字体文件上传到 /tmp 目录："
    echo "  scp msyh.ttc msyhbd.ttc ubuntu@your-server:/tmp/"
    echo ""
    exit 1
fi

echo ""
echo "开始安装字体..."

# 创建字体目录
sudo mkdir -p /usr/share/fonts/truetype/microsoft-yahei

# 复制字体文件
if [ -f "$FONT_DIR/msyh.ttc" ]; then
    sudo cp "$FONT_DIR/msyh.ttc" /usr/share/fonts/truetype/microsoft-yahei/
    echo "✓ 已安装 msyh.ttc"
fi

if [ -f "$FONT_DIR/msyhbd.ttc" ]; then
    sudo cp "$FONT_DIR/msyhbd.ttc" /usr/share/fonts/truetype/microsoft-yahei/
    echo "✓ 已安装 msyhbd.ttc"
fi

if [ -f "$FONT_DIR/msyhl.ttc" ]; then
    sudo cp "$FONT_DIR/msyhl.ttc" /usr/share/fonts/truetype/microsoft-yahei/
    echo "✓ 已安装 msyhl.ttc"
fi

# 设置权限
sudo chmod 644 /usr/share/fonts/truetype/microsoft-yahei/*

# 更新字体缓存
echo ""
echo "更新字体缓存..."
sudo fc-cache -fv

# 验证安装
echo ""
echo "======================================"
echo "验证字体安装："
echo "======================================"
fc-list | grep -i "yahei" || fc-list | grep -i "microsoft"

echo ""
echo "======================================"
echo "安装完成！"
echo "======================================"
echo ""
echo "下一步："
echo "1. 重启 Odoo 服务: sudo systemctl restart odoo"
echo "2. 升级模块: mall_leasing"
echo "3. 测试打印缴费通知单"
echo ""

#!/bin/bash

echo "========================================"
echo "升级 Mall Leasing 模块"
echo "========================================"

# 检查 Odoo 配置文件
ODOO_CONF="/etc/odoo.conf"
if [ ! -f "$ODOO_CONF" ]; then
    ODOO_CONF="/home/ubuntu/odoo.conf"
fi

if [ ! -f "$ODOO_CONF" ]; then
    echo "❌ 找不到 Odoo 配置文件"
    echo "请手动指定配置文件路径："
    echo "  odoo -c /path/to/odoo.conf -u mall_leasing -d your_database --stop-after-init"
    exit 1
fi

echo "📋 使用配置文件: $ODOO_CONF"

# 读取数据库名称
DB_NAME=$(grep "^db_name" $ODOO_CONF | cut -d'=' -f2 | tr -d ' ')

if [ -z "$DB_NAME" ]; then
    echo "⚠️  配置文件中未指定数据库名称"
    read -p "请输入数据库名称: " DB_NAME
fi

echo "📦 数据库: $DB_NAME"
echo ""
echo "🔄 开始升级模块..."
echo ""

# 执行升级
odoo -c $ODOO_CONF -u mall_leasing -d $DB_NAME --stop-after-init

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 模块升级成功！"
    echo ""
    echo "📝 下一步操作："
    echo "1. 重启 Odoo 服务"
    echo "2. 打开 Odoo 并进入会计模块"
    echo "3. 打开任意一张发票查看新字段"
    echo ""
else
    echo ""
    echo "❌ 模块升级失败"
    echo "请查看上面的错误信息"
    echo ""
fi

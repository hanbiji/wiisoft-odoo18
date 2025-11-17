# PDF中文字体支持说明

## 问题说明
Odoo生成PDF时使用wkhtmltopdf工具，如果系统没有安装中文字体，PDF中的中文将无法显示。

## 解决方案

### 方案1：安装中文字体（推荐）

在Ubuntu/Debian系统上安装中文字体：

```bash
sudo apt-get update
sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk
```

在CentOS/RHEL系统上：

```bash
sudo yum install -y wqy-zenhei-fonts wqy-microhei-fonts google-noto-sans-cjk-fonts
```

### 方案2：手动安装特定字体

1. 下载中文字体文件（如SimSun.ttf, Microsoft YaHei.ttf等）
2. 创建字体目录：
```bash
sudo mkdir -p /usr/share/fonts/chinese
```

3. 复制字体文件到目录：
```bash
sudo cp *.ttf /usr/share/fonts/chinese/
```

4. 更新字体缓存：
```bash
sudo fc-cache -fv
```

### 方案3：验证字体安装

检查系统中可用的中文字体：
```bash
fc-list :lang=zh
```

### 方案4：重启Odoo服务

安装字体后，需要重启Odoo服务：
```bash
sudo systemctl restart odoo
# 或
sudo service odoo restart
```

## 已配置的字体回退列表

报表模板已配置以下字体回退顺序：
1. Noto Sans CJK SC（推荐，开源且支持完整）
2. Noto Sans
3. DejaVu Sans
4. SimSun（宋体）
5. Microsoft YaHei（微软雅黑）
6. WenQuanYi Micro Hei（文泉驿微米黑）
7. sans-serif（系统默认）

## 测试

升级模块后打印一份合同，检查中文是否正确显示：
```bash
# 升级模块
odoo-bin -c /path/to/odoo.conf -u mall_leasing -d your_database
```

## 常见问题

**Q: 安装字体后仍然无法显示中文？**
A: 
1. 确认已重启Odoo服务
2. 检查wkhtmltopdf版本（建议使用0.12.5或更高版本）
3. 使用 `fc-list :lang=zh` 确认字体已正确安装

**Q: PDF中部分中文显示为方块？**
A: 字体文件可能不完整或不支持某些字符，建议安装Noto Sans CJK SC字体，它支持最完整的中文字符集。

**Q: 如何更改默认字体？**
A: 编辑 `mall_leasing/report/contract_report.xml` 文件中的CSS样式部分，修改font-family属性。


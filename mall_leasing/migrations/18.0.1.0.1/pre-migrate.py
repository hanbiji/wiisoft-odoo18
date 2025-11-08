# -*- coding: utf-8 -*-

def migrate(cr, version):
    """
    数据迁移：处理 mall_leasing_contract 表中的 NULL 值
    在应用 NOT NULL 约束之前清理数据
    """
    
    # 检查表是否存在
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'mall_leasing_contract'
        );
    """)
    
    if not cr.fetchone()[0]:
        # 表不存在，跳过迁移
        return
    
    # 1. 处理 mall_id 为 NULL 的记录
    # 首先检查是否有默认的商场记录
    cr.execute("SELECT id FROM mall_mall LIMIT 1;")
    mall_result = cr.fetchone()
    
    if mall_result:
        default_mall_id = mall_result[0]
        cr.execute("""
            UPDATE mall_leasing_contract 
            SET mall_id = %s 
            WHERE mall_id IS NULL;
        """, (default_mall_id,))
    else:
        # 如果没有商场记录，删除这些无效的合同记录
        cr.execute("DELETE FROM mall_leasing_contract WHERE mall_id IS NULL;")
    
    # 2. 处理 operator_id 为 NULL 的记录
    # 检查是否有运营单位记录
    cr.execute("""
        SELECT id FROM res_partner 
        WHERE mall_contact_type IN ('operator', 'property_company') 
        LIMIT 1;
    """)
    operator_result = cr.fetchone()
    
    if operator_result:
        default_operator_id = operator_result[0]
        cr.execute("""
            UPDATE mall_leasing_contract 
            SET operator_id = %s 
            WHERE operator_id IS NULL;
        """, (default_operator_id,))
    else:
        # 如果没有运营单位记录，删除这些无效的合同记录
        cr.execute("DELETE FROM mall_leasing_contract WHERE operator_id IS NULL;")
    
    # 3. 处理 shop_name 为 NULL 或空字符串的记录
    cr.execute("""
        UPDATE mall_leasing_contract 
        SET shop_name = '未命名店铺' 
        WHERE shop_name IS NULL OR shop_name = '';
    """)
    
    # 4. 处理 partner_id 为 NULL 的记录（虽然警告中没有提到，但这也是必填字段）
    cr.execute("""
        SELECT id FROM res_partner 
        WHERE mall_contact_type = 'tenant' 
        LIMIT 1;
    """)
    tenant_result = cr.fetchone()
    
    if tenant_result:
        default_tenant_id = tenant_result[0]
        cr.execute("""
            UPDATE mall_leasing_contract 
            SET partner_id = %s 
            WHERE partner_id IS NULL;
        """, (default_tenant_id,))
    else:
        # 如果没有租户记录，删除这些无效的合同记录
        cr.execute("DELETE FROM mall_leasing_contract WHERE partner_id IS NULL;")
    
    # 记录迁移日志
    cr.execute("SELECT COUNT(*) FROM mall_leasing_contract;")
    count = cr.fetchone()[0]
    print(f"数据迁移完成，当前合同记录数：{count}")
/**
 * WiiBoard Gallery - Modal image preview for board_drawing_ids
 * Odoo 18 backend asset
 * 纯DOM实现的轻量级弹窗画廊，避免对OWL/对话服务的依赖。
 */
odoo.define('@clothing_development_approval/js/wiiboard_gallery', [], function (require) {
    'use strict';

    function buildOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'wiiboard-overlay';
        overlay.innerHTML = `
            <style>
                .wiiboard-overlay{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:2000;display:flex;align-items:center;justify-content:center;}
                .wiiboard-box{max-width:90vw;max-height:90vh;color:#fff;}
                .wiiboard-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
                .wiiboard-title{font-weight:600;}
                .wiiboard-count{opacity:.8;font-size:.9rem;}
                .wiiboard-imgwrap{text-align:center}
                .wiiboard-img{max-width:90vw;max-height:70vh;object-fit:contain;border-radius:4px;}
                .wiiboard-actions{display:flex;gap:8px;justify-content:space-between;margin-top:12px}
                .wiiboard-btn{background:#2e2e2e;border:1px solid #555;color:#fff;padding:6px 12px;border-radius:4px;cursor:pointer}
                .wiiboard-btn:hover{background:#3a3a3a}
                .wiiboard-close{position:absolute;top:12px;right:16px;color:#fff;font-size:22px;cursor:pointer}
            </style>
            <div class="wiiboard-box">
                <div class="wiiboard-close" title="关闭">×</div>
                <div class="wiiboard-head">
                    <div class="wiiboard-title"></div>
                    <div class="wiiboard-count"></div>
                </div>
                <div class="wiiboard-imgwrap"><img class="wiiboard-img" alt="preview image"/></div>
                <div class="wiiboard-actions">
                    <button class="wiiboard-btn wiiboard-prev">上一张</button>
                    <button class="wiiboard-btn wiiboard-next">下一张</button>
                    <a class="wiiboard-btn wiiboard-open" target="_blank">新标签打开</a>
                </div>
            </div>`;
        return overlay;
    }

    function openGallery(items, index) {
        let idx = Math.max(0, Math.min(index || 0, items.length - 1));
        const overlay = buildOverlay();
        const title = overlay.querySelector('.wiiboard-title');
        const count = overlay.querySelector('.wiiboard-count');
        const img = overlay.querySelector('.wiiboard-img');
        const openBtn = overlay.querySelector('.wiiboard-open');
        const prevBtn = overlay.querySelector('.wiiboard-prev');
        const nextBtn = overlay.querySelector('.wiiboard-next');
        const closeBtn = overlay.querySelector('.wiiboard-close');

        function render() {
            const item = items[idx];
            title.textContent = item.name || '';
            count.textContent = `${idx + 1} / ${items.length}`;
            img.src = item.src;
            openBtn.href = item.src;
        }
        function prev(){ idx = (idx - 1 + items.length) % items.length; render(); }
        function next(){ idx = (idx + 1) % items.length; render(); }
        function close(){
            document.removeEventListener('keydown', onKey);
            overlay.remove();
        }
        function onKey(e){
            if (e.key === 'ArrowLeft') prev();
            else if (e.key === 'ArrowRight') next();
            else if (e.key === 'Escape') close();
        }

        prevBtn.addEventListener('click', prev);
        nextBtn.addEventListener('click', next);
        closeBtn.addEventListener('click', close);
        overlay.addEventListener('click', (e)=>{ if(e.target === overlay) close(); });
        document.addEventListener('keydown', onKey);

        document.body.appendChild(overlay);
        render();
    }

    function start() {
        // 全局仅绑定一次，避免重复注册
        if (window.__wiiboard_gallery_bound__) return;
        window.__wiiboard_gallery_bound__ = true;
        document.addEventListener('click', function (ev) {
            const a = ev.target && ev.target.closest ? ev.target.closest('a.wiiboard-thumb') : null;
            if (!a) return;
            const scope = a.closest('.wiiboard-gallery');
            if (!scope) return;
            ev.preventDefault();
            const anchors = Array.from(scope.querySelectorAll('a.wiiboard-thumb'));
            const items = anchors.map(el => ({ src: el.dataset.src || el.getAttribute('href'), name: el.dataset.name || el.getAttribute('title') || '' }));
            const index = anchors.indexOf(a);
            openGallery(items, index);
        }, true); // 捕获阶段，早于其他处理
    }

    // 立即启动（资源加载后执行），不依赖 registry/main_components，避免 MutationObserver 报错
    start();
});
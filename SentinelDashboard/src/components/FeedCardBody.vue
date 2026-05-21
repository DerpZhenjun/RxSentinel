<template>
  <div class="card-header">
    <div class="source-tag" :class="item.platformType">[{{ item.platform }}]</div>
    <div class="entity-name" v-if="item.merchant !== '无' && item.merchant !== '未指明'">
      实体：{{ item.merchant }}
    </div>
    <div class="entity-name safe" v-else>实体: 无</div>

    <div class="source-title-block" v-if="isValidUrl(item.source_url)">
      <span class="field-label">来源标题</span>
      <a
        class="source-link"
        :href="item.source_url"
        target="_blank"
        rel="noopener noreferrer"
        title="落地链接：在浏览器中打开该作品/笔记的原始页面（与标题文案无关）"
      >
        🔗 {{ formatTitle(item.video_title) }}
      </a>
      <span
        v-if="store.urlAliveness[item.source_url] === 'dead'"
        class="source-warn source-warn-dead"
        title="服务端判定：该落地页已失效或疑似被平台删除"
      >⚠</span>
    </div>
  </div>

  <div class="card-content">
    <div v-if="item.threadParent" class="thread-parent">
      <span class="thread-label">上一层评论（父评）</span>
      <span class="thread-parent-text">{{ item.threadParent }}</span>
    </div>
    <div v-else-if="item.replyTargetNick" class="thread-parent thread-parent-hint">
      <span class="thread-label">回复 @昵称（正文前缀）</span>
      <span class="thread-at">@{{ item.replyTargetNick }}</span>
      <span class="thread-hint-note">（父评全文未入库或未在同批清洗数据中解析）</span>
    </div>
    <div class="thread-self">
      <span class="thread-self-label">当前评论（本条）</span>
      "{{ item.content }}"
    </div>
  </div>
  <div class="card-analysis">
    <span class="ai-icon">🤖 AI 研判:</span> {{ item.analysis }}
  </div>
</template>

<script setup>
import { useSentinelStore } from '../stores/sentinelStore';

defineProps({
  item: { type: Object, required: true },
  formatTitle: { type: Function, required: true },
  isValidUrl: { type: Function, required: true },
});

const store = useSentinelStore();
</script>

<style scoped>
.card-header { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; margin-bottom: 10px; font-size: 13px; }
.source-title-block { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; margin-left: auto; max-width: min(100%, 320px); justify-content: flex-end; }
.field-label { font-size: 11px; color: #6a9ec4; font-weight: normal; letter-spacing: 0.5px; flex-shrink: 0; }
.source-tag { padding: 2px 6px; border-radius: 3px; margin-right: 10px; font-weight: bold; }
.entity-name { background: rgba(255,77,79,0.2); color: #ff4d4f; border: 1px solid #ff4d4f; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
.entity-name.safe { background: rgba(255,255,255,0.1); color: #aaa; border: 1px solid #555; }
.source-link { color: #8bbce6; text-decoration: none; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color 0.2s; flex-shrink: 0; }
.source-link:hover { color: #00baff; text-decoration: underline; }
.source-warn { font-size: 0.75em; opacity: 0.9; margin-left: 3px; vertical-align: super; font-weight: bold; flex-shrink: 0; cursor: default; }
.source-warn-dead { color: #faad14; }
.card-content { font-size: 14px; line-height: 1.6; color: #d8eeff; margin-bottom: 10px; background: rgba(0,0,0,0.28); padding: 8px; border-radius: 4px; }
.thread-parent { font-size: 12px; color: #9ecfff; margin-bottom: 8px; font-style: normal; line-height: 1.45; word-break: break-word; }
.thread-parent-hint { color: #b8d9f0; }
.thread-parent-text { display: block; margin-top: 4px; white-space: pre-wrap; }
.thread-at { color: #69e0ff; font-weight: 600; }
.thread-hint-note { font-size: 11px; color: #7a9aad; margin-left: 4px; }
.thread-label { display: inline-block; margin-right: 6px; padding: 1px 6px; border-radius: 2px; background: rgba(0,186,255,0.15); color: #00e5ff; font-size: 11px; vertical-align: middle; }
.thread-self { font-style: italic; color: #d8eeff; }
.thread-self-label { display: inline-block; margin-right: 6px; font-size: 11px; font-style: normal; color: #6a9ec4; vertical-align: middle; }
.card-analysis { font-size: 13px; color: #ffd66f; line-height: 1.5; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 8px; }
.ai-icon { font-weight: bold; color: #ff7675; }
</style>

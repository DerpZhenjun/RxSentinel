<template>
  <div class="top-indicators">
    <div class="indicator-card">
      <div class="label">总线索数</div>
      <div class="value">{{ store.totalLeads }}</div>
    </div>
    <div class="indicator-card">
      <div class="label">有效线索数</div>
      <div class="value">{{ store.validLeads }}</div>
    </div>
    <div class="indicator-card">
      <div class="label">高危实体数</div>
      <div class="value">{{ store.totalMerchants }}</div>
    </div>
    <div class="indicator-card">
      <div class="label">覆盖平台数</div>
      <div class="value">{{ store.platformTotal }}</div>
    </div>
  </div>
</template>

<script setup>
/** 顶栏四块 KPI：纯派生自 `rebuildDerivedData`，组件内不做二次聚合 */
import { useSentinelStore } from '../stores/sentinelStore';

const store = useSentinelStore();
</script>

<style scoped>
.top-indicators {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.indicator-card {
  position: relative;
  height: 100%;
  overflow: hidden;
  border: 1px solid rgba(0, 186, 255, 0.28);
  border-radius: 6px;
  background: linear-gradient(180deg, rgba(0, 186, 255, 0.2) 0%, rgba(0, 186, 255, 0.04) 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  box-shadow: inset 0 0 12px rgba(0, 186, 255, 0.12), 0 0 8px rgba(0, 186, 255, 0.12);
  transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}

.indicator-card::before {
  content: '';
  position: absolute;
  width: 40%;
  height: 220%;
  top: -60%;
  left: -60%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.25), transparent);
  transform: rotate(18deg);
  animation: sweep 4.6s linear infinite;
}

.indicator-card:hover {
  transform: translateY(-1px);
  border-color: rgba(0, 229, 255, 0.72);
  box-shadow: inset 0 0 16px rgba(0, 186, 255, 0.16), 0 0 14px rgba(0, 229, 255, 0.24);
}

.label {
  position: relative;
  z-index: 2;
  font-size: 12px;
  color: #9ddaf5;
  letter-spacing: 1px;
  margin-bottom: 6px;
}

.value {
  position: relative;
  z-index: 2;
  font-size: 26px;
  font-weight: 700;
  color: #00e5ff;
  line-height: 1;
  text-shadow: 0 0 12px rgba(0, 229, 255, 0.5);
}

@keyframes sweep {
  0% { left: -60%; }
  100% { left: 130%; }
}
</style>

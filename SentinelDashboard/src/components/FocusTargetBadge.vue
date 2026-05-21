<template>
  <div class="focus-target-badge" aria-label="榜单命中锁定" title="榜单命中锁定">
    <svg class="target-icon-svg" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle class="target-outer" cx="24" cy="24" r="20" />
      <circle class="target-mid" cx="24" cy="24" r="12" />
      <circle class="target-core" cx="24" cy="24" r="5" />
      <path class="target-cross" d="M24 3v8M24 37v8M3 24h8M37 24h8" />
    </svg>
  </div>
</template>

<style scoped>
.focus-target-badge {
  position: absolute;
  top: -14px;
  right: 10px;
  z-index: 2;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  filter: drop-shadow(0 0 10px rgba(255, 235, 59, 0.85));
  animation: target-badge-pulse 1.4s ease-in-out infinite;
}
.target-icon-svg { width: 32px; height: 32px; overflow: visible; }
.target-outer { fill: none; stroke: #00e5ff; stroke-width: 2; opacity: 0.85; }
.target-mid { fill: rgba(255, 235, 59, 0.12); stroke: #ffeb3b; stroke-width: 2.5; }
.target-core { fill: #ff4d4f; stroke: #fff; stroke-width: 1; }
.target-cross { fill: none; stroke: #00e5ff; stroke-width: 2.5; stroke-linecap: round; opacity: 0.9; }
@keyframes target-badge-pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 0 8px rgba(0, 229, 255, 0.6)); }
  50% { transform: scale(1.12); filter: drop-shadow(0 0 14px rgba(255, 235, 59, 0.95)); }
}
</style>

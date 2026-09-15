<script setup>
defineProps({ plan: { type: Object, required: true } })
const labels = { planning: '正在制定计划', running: '正在执行', completed: '已完成', partial: '部分完成', failed: '执行失败', pending: '待执行', blocked: '需要补充信息', skipped: '已跳过', interrupted: '已中断' }
const agents = { research: '资料核实', technical: '技术与分析专家', service: '位置与出行专家' }
</script>

<template>
  <section class="task-progress" aria-label="复杂任务进度" aria-live="polite">
    <strong>任务计划 · {{ labels[plan.status] || plan.status }}</strong>
    <ol>
      <li v-for="step in plan.steps" :key="step.id">
        <span>{{ step.title }}</span>
        <small>{{ agents[step.executor] }} · {{ labels[step.status] || step.status }}</small>
        <p v-if="step.detail">{{ step.detail }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.task-progress { padding: 16px; border: 1px solid #cbd5e1; border-radius: 12px; background: #f8fafc; color: #334155; }
ol { padding-left: 22px; margin-bottom: 0; }
li { margin: 12px 0; }
small { display: block; color: #64748b; margin-top: 4px; }
p { margin: 4px 0; font-size: 13px; }
</style>

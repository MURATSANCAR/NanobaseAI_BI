<script setup>
defineProps({ size: { type: Number, default: 18 } });
</script>

<template>
	<svg
		:width="size"
		:height="size"
		viewBox="0 0 118 118"
		class="shrink-0"
		role="img"
		aria-label="ZEKİ AI"
	>
		<defs>
    <linearGradient id="nb-flow-g" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#FF6B4A"/>
      <stop offset="1" stop-color="#7C5CFF"/>
    </linearGradient>
  </defs>
  <rect width="118" height="118" rx="28" fill="url(#nb-flow-g)"/>
  <path d="M32 30h54v11L48 77h38v11H32V77l38-36H32z" fill="#fff"/>
	</svg>
</template>

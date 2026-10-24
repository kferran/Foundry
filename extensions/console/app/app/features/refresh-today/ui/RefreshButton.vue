<script setup lang="ts">
import { Button } from '@/shared/ui'

defineProps<{ busy: boolean }>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <Button :disabled="busy" @click="$emit('refresh')">{{ busy ? 'Refreshing' : 'Refresh' }}</Button>
</template>

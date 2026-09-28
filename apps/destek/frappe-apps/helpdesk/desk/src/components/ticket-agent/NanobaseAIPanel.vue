<template>
  <!-- NanobaseAI: sınıflama sonucu, yazışma özeti, yanıt taslağı, makale taslağı.
       Arka uç: nanobase_brand/yz/kayit.py. Model hiçbir şeyi müşteriye göndermez. -->
  <Section label="NanobaseAI" v-model:opened="opened">
    <div class="space-y-3 pb-3 pt-0.5 text-p-sm text-ink-gray-7">
      <div v-if="info.duygu" class="flex items-center gap-2">
        <span class="text-ink-gray-5">{{ __("Customer mood") }}</span>
        <Badge :label="info.duygu" :theme="moodTheme" variant="subtle" />
      </div>
      <p v-if="info.not" class="text-ink-gray-6">{{ info.not }}</p>

      <div class="space-y-1.5">
        <div class="flex items-center justify-between gap-2">
          <span class="text-ink-gray-5">{{ __("Summary") }}</span>
          <Button
            size="sm"
            variant="ghost"
            :loading="summary.loading"
            :label="info.ozet ? __('Refresh') : __('Summarize')"
            @click="summary.submit({ ticket: ticketId })"
          />
        </div>
        <p v-if="info.ozet" class="whitespace-pre-line leading-5 text-ink-gray-8">
          {{ info.ozet }}
        </p>
      </div>

      <div class="space-y-1.5">
        <Button
          class="w-full"
          variant="solid"
          :loading="draft.loading"
          :label="__('Draft a reply')"
          @click="draft.submit({ ticket: ticketId })"
        />
        <div v-if="sources.length" class="leading-5 text-ink-gray-5">
          {{ __("Based on") }}:
          <template v-for="(s, i) in sources" :key="s.tur + s.ad">
            <span v-if="i">, </span>
            <a :href="sourceLink(s)" target="_blank" class="underline">{{ sourceLabel(s) }}</a>
          </template>
        </div>
      </div>

      <!-- Benzer geçmiş kayıtlar ve onlarda uygulanan çözüm (nanobase_brand.yz.kayit.similar) -->
      <div class="space-y-1.5">
        <div class="flex items-center justify-between gap-2">
          <span class="text-ink-gray-5">{{ __("Similar past tickets") }}</span>
          <Button
            size="sm"
            variant="ghost"
            :loading="similar.loading"
            :label="similar.data ? __('Refresh') : __('Find')"
            @click="similar.submit({ ticket: ticketId })"
          />
        </div>
        <template v-if="similar.data">
          <p v-if="!similar.data.kayitlar.length" class="text-ink-gray-5">
            {{ __("No similar resolved ticket yet.") }}
          </p>
          <div v-if="similar.data.oneri.length" class="rounded-md bg-surface-gray-2 p-2">
            <div class="mb-1 font-medium text-ink-gray-8">{{ __("Suggested approach") }}</div>
            <ul class="list-disc space-y-0.5 ps-4 leading-5">
              <li v-for="(line, i) in similar.data.oneri" :key="i">{{ line }}</li>
            </ul>
          </div>
          <ul class="space-y-2">
            <li v-for="t in similar.data.kayitlar" :key="t.ad" class="leading-5">
              <a :href="`/helpdesk/tickets/${t.ad}`" target="_blank" class="font-medium text-ink-gray-8 underline">
                #{{ t.ad }}</a>
              <span class="text-ink-gray-8"> {{ t.konu }}</span>
              <span class="text-ink-gray-5"> · {{ t.tarih }}</span>
              <div v-if="t.uygulanan" class="text-ink-gray-6">{{ t.uygulanan }}</div>
            </li>
          </ul>
          <p v-if="similar.data.yontem === 'tür' && similar.data.kayitlar.length" class="text-ink-gray-5">
            {{ __("Shown by ticket type; the knowledge base has no close match yet.") }}
          </p>
        </template>
      </div>

      <template v-if="info.cozuldu">
        <Button
          v-if="!info.makale"
          class="w-full"
          variant="subtle"
          :loading="article.loading"
          :label="__('Draft a knowledge base article')"
          @click="article.submit({ ticket: ticketId })"
        />
        <a
          v-else
          :href="`/helpdesk/kb/articles/${info.makale}`"
          class="block text-center underline"
        >{{ __("Open article draft") }}</a>
      </template>
    </div>
  </Section>
</template>

<script setup lang="ts">
import { replyComposer, showEmailBox, toggleEmailBox } from "@/pages/ticket/modalStates";
import { __ } from "@/translation.ts";
import { TicketSymbol } from "@/types";
import { Badge, Button, createResource, toast } from "frappe-ui";
import { computed, inject, nextTick, ref, watch } from "vue";
import Section from "../Section.vue";

type Source = { tur: "makale" | "kayit"; ad: string; baslik?: string };
type Info = {
  duygu?: string;
  not?: string;
  ozet?: string;
  ozet_zamani?: string;
  cozuldu?: boolean;
  makale?: string | null;
};

const ticket = inject(TicketSymbol)!;
const ticketId = computed(() => ticket.value?.name);
const opened = ref(true);
const sources = ref<Source[]>([]);

const panel = createResource({
  url: "nanobase_brand.yz.kayit.panel",
  makeParams: () => ({ ticket: ticketId.value }),
});
const info = computed<Info>(() => panel.data || {});

// Kayıt değişince (durum, sınıflama sonucu) panel yeniden okunur.
watch(
  () => [ticketId.value, ticket.value?.doc?.status, ticket.value?.doc?.modified],
  () => ticketId.value && panel.reload(),
  { immediate: true }
);

const moodTheme = computed(
  () =>
    ({ Olumlu: "green", Nötr: "gray", Olumsuz: "orange", Öfkeli: "red" } as Record<string, string>)[
      info.value.duygu || ""
    ] || "gray"
);

function failed(error: any) {
  toast.error(error?.messages?.[0] || __("The assistant is unavailable right now. Please try again shortly."));
}

const summary = createResource({
  url: "nanobase_brand.yz.kayit.summarize",
  onSuccess: () => panel.reload(),
  onError: failed,
});

const draft = createResource({
  url: "nanobase_brand.yz.kayit.draft_reply",
  onError: failed,
  async onSuccess(data: { html: string; kaynaklar: Source[] }) {
    sources.value = data.kaynaklar || [];
    // Hazır yanıt gibi: yanıt kutusu açılır, taslak başa eklenir; gönderen temsilcidir.
    if (!showEmailBox.value) toggleEmailBox();
    await nextTick();
    const insert = replyComposer.value;
    if (!insert) {
      toast.error(__("Could not open the reply box"));
      return;
    }
    insert({ title: "NanobaseAI", message: data.html, actions: [] });
    toast.success(__("Draft added to the reply. Review it before sending."));
  },
});

const similar = createResource({
  url: "nanobase_brand.yz.kayit.similar",
  onError: failed,
});

// Başka kayda geçilince önceki kaydın benzerleri kalmasın.
watch(ticketId, () => similar.reset());

const article = createResource({
  url: "nanobase_brand.yz.kayit.article_draft",
  onError: failed,
  onSuccess(data: { name: string }) {
    panel.reload();
    toast.success(__("Article draft created"));
    window.open(`/helpdesk/kb/articles/${data.name}`, "_blank");
  },
});

function sourceLink(s: Source) {
  return s.tur === "makale" ? `/helpdesk/kb/articles/${s.ad}` : `/helpdesk/tickets/${s.ad}`;
}

function sourceLabel(s: Source) {
  return s.tur === "makale" ? s.baslik || s.ad : `#${s.ad}`;
}
</script>

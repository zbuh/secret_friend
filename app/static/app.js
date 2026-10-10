"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  },
};

function toast(text, ms = 2600) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("show"), ms);
}

async function api(url, method = "POST", body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = "Verifica os campos: " + msg.map((d) => d.loc.slice(1).join(" ")).join(", ");
    throw new Error(msg || "Algo correu mal. Tenta outra vez.");
  }
  return data;
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const t = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(t); t.select(); document.execCommand("copy"); t.remove();
  }
  toast("Link copiado 📋");
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy]");
  if (btn) copy(btn.dataset.copy);
});

// Pretty dates
$$("[data-date]").forEach((el) => {
  const d = new Date(el.dataset.date + "T12:00:00");
  if (!isNaN(d)) el.textContent = "📅 " + d.toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" }) + (el.dataset.time ? ` · ${el.dataset.time}` : "");
});
$$("[data-datetime]").forEach((el) => {
  const d = new Date(el.dataset.datetime);
  if (!isNaN(d)) el.textContent = d.toLocaleString("pt-PT", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
});

// ---------- Create page ----------
function initCreate() {
  const form = $("#create-form");
  const list = $("#people");
  const tpl = $("#person-tpl");
  const DRAFT = "sf-draft";

  function addPerson(p = {}, focus = false) {
    const row = tpl.content.firstElementChild.cloneNode(true);
    $(".p-name", row).value = p.name || "";
    $(".p-email", row).value = p.email || "";
    $(".p-group", row).value = p.group || "";
    $(".p-manager", row).checked = !!p.manager;
    list.append(row);
    if (focus) $(".p-name", row).focus();
    refresh();
    return row;
  }

  function people() {
    return $$(".person", list).map((row) => ({
      name: $(".p-name", row).value.trim(),
      email: $(".p-email", row).value.trim(),
      group: $(".p-group", row).value.trim(),
      manager: $(".p-manager", row).checked,
    }));
  }

  function refresh() {
    const ps = people().filter((p) => p.name);
    $("#count").textContent = ps.length;
    const groups = [...new Set(ps.map((p) => p.group).filter(Boolean))];
    $("#groups").replaceChildren(...groups.map((g) => Object.assign(document.createElement("option"), { value: g })));
    saveDraft();
  }

  function saveDraft() {
    const data = Object.fromEntries(new FormData(form));
    delete data.manager;
    store.set(DRAFT, { ...data, participants: people() });
  }

  list.addEventListener("input", refresh);
  list.addEventListener("change", refresh);

  // 24h time picker: two selects feeding the hidden event_time field
  const hour = $("#hour"), minute = $("#minute"), time = form.elements.event_time;
  const syncTime = () => {
    time.value = hour.value ? `${hour.value}:${minute.value}` : "";
    minute.disabled = !hour.value;
    saveDraft();
  };
  hour.onchange = minute.onchange = syncTime;
  form.addEventListener("input", saveDraft);
  list.addEventListener("click", (e) => {
    if (e.target.closest(".remove")) {
      e.target.closest(".person").remove();
      if (!$(".person", list)) addPerson();
      refresh();
    }
  });
  list.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const row = e.target.closest(".person");
      if (row === list.lastElementChild) addPerson({}, true);
      else $(".p-name", row.nextElementSibling).focus();
    }
  });

  $("#add-person").onclick = () => addPerson({}, true);
  $("#paste-toggle").onclick = () => {
    const box = $("#paste-box");
    box.hidden = !box.hidden;
    if (!box.hidden) $("#paste-text").focus();
  };
  $("#paste-apply").onclick = () => {
    const lines = $("#paste-text").value.split(/\n/).map((l) => l.trim()).filter(Boolean);
    // drop empty rows before appending
    $$(".person", list).forEach((row) => { if (!$(".p-name", row).value.trim()) row.remove(); });
    lines.forEach((line) => {
      const [name, email = "", group = ""] = line.split(/[,;\t]/).map((s) => s.trim());
      if (name) addPerson({ name, email, group });
    });
    $("#paste-text").value = "";
    $("#paste-box").hidden = true;
    toast(`${lines.length} pessoas adicionadas`);
  };

  // Restore draft
  const draft = store.get(DRAFT, null);
  if (draft) {
    for (const [k, v] of Object.entries(draft)) if (form.elements[k] && !["participants", "manager"].includes(k)) form.elements[k].value = v;
    (draft.participants || []).forEach((p) => addPerson(p));
  }
  while ($$(".person", list).length < 3) addPerson();
  if (/^\d{2}:\d{2}$/.test(time.value)) {
    hour.value = time.value.slice(0, 2);
    minute.value = time.value.slice(3);
    if (!minute.value) minute.value = "00";
    syncTime();
  }
  minute.disabled = !hour.value;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#form-error");
    err.hidden = true;
    const data = Object.fromEntries(new FormData(form));
    delete data.manager;
    const participants = people().filter((p) => p.name || p.email);

    let problem = null;
    if (!data.title.trim()) problem = "Dá um nome ao evento.";
    else if (participants.some((p) => !p.name)) problem = "Há uma linha com email mas sem nome.";
    else if (participants.length < 3) problem = "São precisas pelo menos 3 pessoas.";
    else if (participants.some((p) => p.email && !/^\S+@\S+\.\S+$/.test(p.email))) problem = "Há um email que não parece válido.";
    else if (!participants.some((p) => p.manager)) problem = "Marca quem é o gestor 👑 — recebe por email o link para gerir o sorteio.";
    else if (participants.some((p) => p.manager && !p.email)) problem = "O gestor precisa de email, para receber o link de gestão.";
    if (problem) { err.textContent = problem; err.hidden = false; return; }

    const btn = $("#submit");
    btn.disabled = true;
    btn.textContent = "A sortear…";
    try {
      const res = await api("/api/events", "POST", { ...data, participants });
      try { localStorage.removeItem(DRAFT); } catch {}
      location.href = res.admin_url;
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
      btn.disabled = false;
      btn.textContent = "🎲 Sortear";
    }
  });

  $("#discard").onclick = () => {
    if (!confirm("Limpar tudo o que escreveste?")) return;
    try { localStorage.removeItem(DRAFT); } catch {}
    location.reload();
  };
}

// ---------- Login / home ----------
function initLogin() {
  const form = $("#login-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("#login-error");
    err.hidden = true;
    try {
      await api("/api/login", "POST", { password: form.elements.password.value });
      location.reload();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

function initHome() {
  $$("[data-date-short]").forEach((el) => {
    const d = new Date(el.dataset.dateShort + "T12:00:00");
    if (!isNaN(d)) el.textContent = d.toLocaleDateString("pt-PT", { day: "numeric", month: "short", year: "numeric" });
  });

  const draft = store.get("sf-draft", null);
  if (draft && (draft.title || (draft.participants || []).some((p) => p.name))) {
    $("#draft").hidden = false;
    $("#draft-title").textContent = draft.title || "sem nome";
  }

  $("#logout-admin").onclick = async () => {
    await api("/api/logout").catch(() => {});
    location.reload();
  };
}

// ---------- Admin page ----------
function initAdmin() {
  const root = $("#admin");
  const adminPath = new URL(root.dataset.adminUrl).pathname;
  const apiBase = `/api/events${adminPath.slice(2)}`;
  const title = root.dataset.title;

  async function sendEmails(ids, btn) {
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "A enviar…";
    try {
      const res = await api(`${apiBase}/email`, "POST", { ids });
      if (res.failed.length) toast(`Enviados: ${res.sent}. Falharam: ${res.failed.join(", ")}`, 6000);
      else toast(res.sent ? `${res.sent} email(s) enviado(s) ✉️` : "Já todos receberam o email.");
      setTimeout(() => location.reload(), 1500);
    } catch (ex) {
      toast(ex.message, 6000);
      btn.disabled = false;
      btn.textContent = label;
    }
  }

  $$(".email-one").forEach((btn) => {
    btn.onclick = () => sendEmails([Number(btn.closest(".item").dataset.id)], btn);
  });
  const all = $("#email-all");
  if (all) all.onclick = () => sendEmails(null, all);

  $$(".release").forEach((btn) => {
    btn.onclick = async () => {
      const { id, name } = btn.closest(".item").dataset;
      if (!confirm(`Libertar o nome «${name}»? Quem o escolheu perde o acesso, e o nome fica livre para ser escolhido outra vez.`)) return;
      try {
        await api(`${apiBase}/release/${id}`);
        toast("Nome libertado");
        setTimeout(() => location.reload(), 800);
      } catch (ex) { toast(ex.message, 6000); }
    };
  });

  $("#redraw").onclick = async () => {
    if (!confirm("Refazer o sorteio? Os pares atuais desaparecem (o link mantém-se).")) return;
    try {
      await api(`${apiBase}/redraw`);
      toast("Sorteio refeito 🎲");
    } catch (ex) { toast(ex.message, 6000); }
  };

  $("#close").onclick = async () => {
    if (!confirm(`Terminar «${title}»? Os pares ficam visíveis aqui, como lembrança.`)) return;
    try {
      await api(`${apiBase}/close`);
      location.reload();
    } catch (ex) { toast(ex.message, 6000); }
  };

  $("#delete").onclick = async () => {
    if (!confirm(`Apagar «${title}»? O link deixa de funcionar para todos.`)) return;
    try {
      await api(apiBase, "DELETE");
      location.href = "/";
    } catch (ex) { toast(ex.message, 6000); }
  };
}

// ---------- Memory page (past draws) ----------
function initMemory() {
  const root = $("#memory");
  const { api: apiBase, title } = root.dataset;
  const reopen = $("#reopen");
  if (reopen) reopen.onclick = async () => {
    if (!confirm(`Reabrir «${title}»? Os pares voltam a ficar escondidos.`)) return;
    try {
      await api(`${apiBase}/reopen`);
      location.reload();
    } catch (ex) { toast(ex.message, 6000); }
  };
  $("#delete").onclick = async () => {
    if (!confirm(`Apagar «${title}»? Esta lembrança desaparece para sempre.`)) return;
    try {
      await api(apiBase, "DELETE");
      location.href = "/";
    } catch (ex) { toast(ex.message, 6000); }
  };
}

// ---------- Share page (pick your name) ----------
function initShare() {
  const share = $("#share").dataset.share;
  const KEY = `sf-me-${share}`;
  const dialog = $("#pin-dialog");
  const pin = $("#pin");
  const err = $("#pin-error");
  let current = null;

  const saved = store.get(KEY, null);
  if (saved) {
    const link = $("#continue");
    link.href = saved.url;
    $("#continue-name").textContent = saved.name;
    link.hidden = false;
  }

  $$(".name-btn").forEach((btn) => {
    btn.onclick = () => {
      if (btn.dataset.byEmail === "true") {
        toast(`${btn.dataset.name} recebeu um link pessoal por email — usa esse link. Não o encontras? Procura no spam ou fala com o gestor.`, 7000);
        return;
      }
      current = btn.dataset;
      const claimed = current.claimed === "true";
      $("#pin-title").textContent = claimed ? `Olá de novo, ${current.name}!` : `És ${current.name}?`;
      $("#pin-hint").textContent = claimed
        ? "Escreve o PIN que escolheste da primeira vez. Não és tu? Fala com o organizador."
        : "Escolhe um PIN de 4 dígitos e guarda-o: serve para voltares a ver o resultado noutro telemóvel ou computador.";
      $("#pin-submit").textContent = claimed ? "Entrar" : "Sou eu, continuar";
      pin.value = "";
      err.hidden = true;
      dialog.showModal();
      pin.focus();
    };
  });

  $("#pin-cancel").onclick = () => dialog.close();
  pin.addEventListener("input", () => { pin.value = pin.value.replace(/\D/g, "").slice(0, 4); });

  $("#pin-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!/^\d{4}$/.test(pin.value)) {
      err.textContent = "O PIN tem de ter 4 dígitos.";
      err.hidden = false;
      return;
    }
    const btn = $("#pin-submit");
    btn.disabled = true;
    try {
      const res = await api(`/api/s/${share}/claim`, "POST", { participant_id: Number(current.id), pin: pin.value });
      store.set(KEY, { url: res.url, name: res.name });
      location.href = res.url;
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
      btn.disabled = false;
    }
  });
}

// ---------- Participant page ----------
function initParticipant() {
  const card = $("#reveal");
  const token = card.dataset.token;
  const { share, name, title } = card.dataset;
  store.set(`sf-me-${share}`, { url: location.pathname, name, title });

  function show(name, animate) {
    $("#target-name").textContent = name;
    card.classList.add("opened");
    if (animate) card.classList.add("animate");
    $("#result").hidden = false;
    if (animate) confetti();
  }

  if (card.dataset.revealed === "true") {
    show($("#target-name").textContent, false);
  } else {
    $("#gift").onclick = async () => {
      $("#gift").disabled = true;
      $("#gift").classList.add("shake");
      try {
        const [res] = await Promise.all([
          api(`/api/p/${token}/reveal`),
          new Promise((r) => setTimeout(r, 900)),
        ]);
        show(res.name, true);
      } catch (ex) {
        toast(ex.message, 6000);
        $("#gift").disabled = false;
      }
      $("#gift").classList.remove("shake");
    };
  }

  const logout = $("#logout");
  if (logout) logout.onclick = () => { try { localStorage.removeItem(`sf-me-${logout.dataset.share}`); } catch {} };
}

function confetti() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const colors = ["#c0392b", "#1e7a4f", "#e6b422", "#ffffff", "#2a6fdb"];
  const layer = document.createElement("div");
  layer.className = "confetti";
  for (let i = 0; i < 90; i++) {
    const p = document.createElement("i");
    p.style.left = Math.random() * 100 + "vw";
    p.style.background = colors[i % colors.length];
    p.style.animationDelay = Math.random() * 0.4 + "s";
    p.style.animationDuration = 1.8 + Math.random() * 1.6 + "s";
    p.style.setProperty("--x", (Math.random() - 0.5) * 200 + "px");
    p.style.setProperty("--r", Math.random() * 720 + "deg");
    layer.append(p);
  }
  document.body.append(layer);
  setTimeout(() => layer.remove(), 4000);
}

({ login: initLogin, home: initHome, create: initCreate, admin: initAdmin, memory: initMemory, share: initShare, participant: initParticipant })[document.body.dataset.page]?.();

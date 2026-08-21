document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();

    let chartInstance = null;
    let currentComparisonData = null;
    let healPollTimer = null;

    const PHASE_MAP = {
        idle: [],
        scrape: ["scrape"],
        health_fail: ["scrape", "health"],
        healing: ["scrape", "health", "heal"],
        retry: ["scrape", "health", "heal"],
        healthy: ["scrape", "health", "heal"],
        indexing: ["scrape", "health", "heal", "index"],
        done: ["scrape", "health", "heal", "index"],
        error: ["scrape"],
    };

    const tabChat = document.getElementById("tab-chat");
    const tabCompare = document.getElementById("tab-compare");
    const viewChat = document.getElementById("view-chat");
    const viewCompare = document.getElementById("view-compare");

    const chatUrlInput = document.getElementById("chat-url-input");
    const chatForm = document.getElementById("chat-form");
    const userInput = document.getElementById("user-input");
    const chatMessages = document.getElementById("chat-messages");
    const sendBtn = document.getElementById("send-btn");

    const compareForm = document.getElementById("compare-form");
    const urlAInput = document.getElementById("url-a");
    const urlBInput = document.getElementById("url-b");
    const topicInput = document.getElementById("topic");
    const compareProgress = document.getElementById("compare-progress");
    const compareResult = document.getElementById("compare-result");
    const resultMarkdown = document.getElementById("result-markdown");
    const compareCitations = document.getElementById("compare-citations");
    const compareError = document.getElementById("compare-error");

    const btnExportPdf = document.getElementById("btn-export-pdf");
    const btnExportMd = document.getElementById("btn-export-md");
    const btnRunHealthy = document.getElementById("btn-run-healthy");
    const btnTriggerHeal = document.getElementById("btn-trigger-heal");
    const demoLogBox = document.getElementById("demo-log");

    tabChat.addEventListener("click", () => {
        tabChat.classList.add("active");
        tabCompare.classList.remove("active");
        viewChat.classList.remove("hidden");
        viewCompare.classList.add("hidden");
    });

    tabCompare.addEventListener("click", () => {
        tabCompare.classList.add("active");
        tabChat.classList.remove("active");
        viewCompare.classList.remove("hidden");
        viewChat.classList.add("hidden");
    });

    chatUrlInput.addEventListener("input", () => {
        const val = chatUrlInput.value.trim();
        if (val) userInput.placeholder = `Ask a question about ${val}…`;
    });

    async function fetchStatus() {
        try {
            const res = await fetch("/api/status");
            if (!res.ok) return;
            const data = await res.json();
            document.getElementById("chunks-count").textContent = data.indexed_chunks;
            document.getElementById("pages-count").textContent = data.baseline_pages;
            document.getElementById("llm-badge").textContent = data.llm_provider || "—";
            const collectorEl = document.getElementById("collector-id");
            if (collectorEl) collectorEl.textContent = data.collector_id || "—";
            const engineEl = document.getElementById("scrape-engine");
            if (engineEl) engineEl.textContent = data.scrape_engine || "—";
            const healLine = document.getElementById("last-heal-line");
            if (healLine) {
                healLine.textContent = data.last_heal_at
                    ? `Last heal: ${data.last_heal_at}`
                    : "Last heal: —";
            }
            const studioLink = document.getElementById("studio-link");
            if (studioLink && data.collector_id) {
                studioLink.href = `https://brightdata.com/cp/scrapers/${data.collector_id}`;
            }

            const statusDot = document.getElementById("status-dot");
            const statusText = document.getElementById("status-text");
            if (data.indexed_chunks > 0) {
                statusDot.className = "status-dot green";
                statusText.textContent = `Indexed · ${data.indexed_chunks} chunks`;
            } else {
                statusDot.className = "status-dot yellow";
                statusText.textContent = "Index empty — run scrape";
            }
        } catch (err) {
            console.error("Failed to fetch status", err);
        }
    }

    function setTimelineFromPhase(phase, healthFailed) {
        const doneThrough = PHASE_MAP[phase] || [];
        document.querySelectorAll(".tl-step").forEach((el) => {
            const key = el.dataset.phase;
            el.classList.remove("active", "done", "fail");
            if (doneThrough.includes(key)) {
                if (key === "health" && (phase === "health_fail" || healthFailed)) {
                    el.classList.add("fail");
                } else if (doneThrough[doneThrough.length - 1] === key && phase !== "done") {
                    el.classList.add("active");
                } else {
                    el.classList.add("done");
                }
            }
            if (phase === "done") el.classList.add("done");
            if (phase === "error" && key === "scrape") el.classList.add("fail");
        });
    }

    async function pollHealStatus() {
        try {
            const res = await fetch("/api/heal-status");
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    }

    function startHealPolling() {
        if (healPollTimer) clearInterval(healPollTimer);
        healPollTimer = setInterval(async () => {
            const st = await pollHealStatus();
            if (!st) return;
            const phase = st.phase || "idle";
            setTimelineFromPhase(phase, phase === "health_fail");
            demoLogBox.classList.remove("hidden");
            const lines = [
                `phase: ${phase}`,
                st.collector_id ? `collector: ${st.collector_id}` : null,
                st.attempt != null ? `attempt: ${st.attempt}` : null,
                st.engine ? `engine: ${st.engine}` : null,
                st.health_reason ? `health: ${st.health_reason.slice(0, 180)}` : null,
                st.message || null,
                st.updated_at ? `updated: ${st.updated_at}` : null,
            ].filter(Boolean);
            demoLogBox.textContent = lines.join("\n");
            await fetchStatus();
            if (phase === "done" || phase === "error") {
                clearInterval(healPollTimer);
                healPollTimer = null;
            }
        }, 2000);
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = userInput.value.trim();
        const targetUrl = chatUrlInput.value.trim() || "https://duckdb.org/docs/";
        if (!query) return;

        appendMessage("user", query);
        userInput.value = "";
        sendBtn.disabled = true;
        const loadingId = appendLoadingMessage(targetUrl);

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, url: targetUrl }),
            });
            removeMessage(loadingId);
            if (res.ok) {
                const data = await res.json();
                appendMessage("assistant", data.answer, data.citations);
            } else {
                const errData = await res.json().catch(() => ({}));
                appendMessage("assistant", `Error: ${errData.detail || "Failed to process chat query"}`);
            }
        } catch (err) {
            removeMessage(loadingId);
            appendMessage("assistant", `Network error: ${err.message}`);
        } finally {
            sendBtn.disabled = false;
            fetchStatus();
        }
    });

    function appendMessage(role, text, citations = []) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}-message`;

        const avatarDiv = document.createElement("div");
        avatarDiv.className = `avatar ${role === "user" ? "av-user" : "av-bot"}`;
        avatarDiv.textContent = role === "user" ? "You" : "SV";

        const contentDiv = document.createElement("div");
        contentDiv.className = role === "assistant" ? "message-content markdown-body" : "message-content";

        if (role === "assistant" && window.marked) {
            contentDiv.innerHTML = marked.parse(text);
        } else {
            const p = document.createElement("p");
            p.textContent = text;
            contentDiv.appendChild(p);
        }

        if (citations && citations.length > 0) {
            const citationsBox = document.createElement("div");
            citationsBox.className = "citations-box";
            const title = document.createElement("div");
            title.className = "citations-title";
            title.textContent = "Source citations";
            citationsBox.appendChild(title);
            const list = document.createElement("div");
            list.className = "citations-list";
            citations.forEach((cit) => {
                const a = document.createElement("a");
                a.className = "citation-pill";
                a.href = cit.url;
                a.target = "_blank";
                a.rel = "noopener";
                a.textContent = `[${cit.id}] ${cit.title}`;
                list.appendChild(a);
            });
            citationsBox.appendChild(list);
            contentDiv.appendChild(citationsBox);
        }

        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendLoadingMessage(targetUrl) {
        const id = "loading-" + Date.now();
        const msgDiv = document.createElement("div");
        msgDiv.className = "message assistant-message";
        msgDiv.id = id;
        const avatarDiv = document.createElement("div");
        avatarDiv.className = "avatar av-bot";
        avatarDiv.textContent = "SV";
        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";
        contentDiv.innerHTML = `<p>Retrieving from index for <b>${targetUrl}</b>…</p>`;
        msgDiv.appendChild(avatarDiv);
        msgDiv.appendChild(contentDiv);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return id;
    }

    function removeMessage(id) {
        const elem = document.getElementById(id);
        if (elem) elem.remove();
    }

    function renderComparisonChart(compA, compB, scoresA, scoresB) {
        const ctx = document.getElementById("comparison-chart").getContext("2d");
        if (chartInstance) chartInstance.destroy();

        chartInstance = new Chart(ctx, {
            type: "radar",
            data: {
                labels: [
                    "Code examples",
                    "Structure depth",
                    "Content volume",
                    "API / reference signal",
                    "Source diversity",
                ],
                datasets: [
                    {
                        label: compA,
                        data: scoresA || [50, 50, 50, 50, 50],
                        fill: true,
                        backgroundColor: "rgba(26, 158, 143, 0.22)",
                        borderColor: "#2dd4bf",
                        pointBackgroundColor: "#2dd4bf",
                    },
                    {
                        label: compB,
                        data: scoresB || [50, 50, 50, 50, 50],
                        fill: true,
                        backgroundColor: "rgba(212, 196, 168, 0.2)",
                        borderColor: "#d4c4a8",
                        pointBackgroundColor: "#d4c4a8",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        angleLines: { color: "rgba(212, 196, 168, 0.15)" },
                        grid: { color: "rgba(212, 196, 168, 0.12)" },
                        pointLabels: {
                            color: "#9aa49c",
                            font: { family: "IBM Plex Sans", size: 11 },
                        },
                        ticks: { display: false, min: 0, max: 100 },
                    },
                },
                plugins: {
                    legend: {
                        labels: {
                            color: "#eceae4",
                            font: { family: "IBM Plex Sans", size: 12 },
                        },
                    },
                },
            },
        });
    }

    compareForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const urlA = urlAInput.value.trim();
        const urlB = urlBInput.value.trim();
        const topic = topicInput.value.trim();
        if (!urlA || !urlB || !topic) return;

        compareError.classList.add("hidden");
        compareError.textContent = "";
        compareProgress.classList.remove("hidden");
        compareResult.classList.add("hidden");
        resetProgressSteps();
        setStepStatus(1, "active");

        try {
            const res = await fetch("/api/scrape-and-compare", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url_a: urlA, url_b: urlB, topic }),
            });

            setStepStatus(1, "done");
            setStepStatus(2, "done");
            setStepStatus(3, "active");

            if (res.ok) {
                const data = await res.json();
                currentComparisonData = data;
                setStepStatus(3, "done");
                setStepStatus(4, "active");
                setStepStatus(4, "done");

                if (window.marked) {
                    resultMarkdown.innerHTML = marked.parse(data.comparison_markdown);
                } else {
                    resultMarkdown.innerText = data.comparison_markdown;
                }

                renderComparisonChart(
                    data.competitor_a,
                    data.competitor_b,
                    data.scores_a,
                    data.scores_b
                );

                if (data.citations && data.citations.length > 0) {
                    compareCitations.innerHTML = `
                        <div class="citations-title">Verified source citations</div>
                        <div class="citations-list">
                            ${data.citations
                                .map(
                                    (c) =>
                                        `<a href="${c.url}" target="_blank" rel="noopener" class="citation-pill">[${c.id}] ${c.title}</a>`
                                )
                                .join("")}
                        </div>`;
                } else {
                    compareCitations.innerHTML = "";
                }

                compareResult.classList.remove("hidden");
                fetchStatus();
            } else {
                const errData = await res.json().catch(() => ({}));
                compareError.textContent = errData.detail || "Compare failed";
                compareError.classList.remove("hidden");
                resetProgressSteps();
            }
        } catch (err) {
            compareError.textContent = `Network error: ${err.message}`;
            compareError.classList.remove("hidden");
            resetProgressSteps();
        }
    });

    function resetProgressSteps() {
        for (let i = 1; i <= 4; i++) {
            const step = document.getElementById(`step-${i}`);
            if (step) step.className = "progress-step";
        }
    }

    function setStepStatus(stepNum, status) {
        const step = document.getElementById(`step-${stepNum}`);
        if (step) step.className = `progress-step ${status}`;
    }

    btnExportMd.addEventListener("click", () => {
        if (!currentComparisonData) return;
        let mdContent = `# Competitive documentation report: ${currentComparisonData.competitor_a} vs ${currentComparisonData.competitor_b}\n\n`;
        mdContent += `**Topic**: ${currentComparisonData.topic}\n\n`;
        mdContent += currentComparisonData.comparison_markdown + "\n\n";
        mdContent += `## Source citations\n`;
        (currentComparisonData.citations || []).forEach((c) => {
            mdContent += `- [${c.title}](${c.url})\n`;
        });
        const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `Doc_Comparison_${currentComparisonData.competitor_a}_vs_${currentComparisonData.competitor_b}.md`;
        link.click();
    });

    btnExportPdf.addEventListener("click", () => {
        if (!currentComparisonData || !window.html2pdf) return;
        const opt = {
            margin: 0.5,
            filename: `Doc_Comparison_${currentComparisonData.competitor_a}_vs_${currentComparisonData.competitor_b}.pdf`,
            image: { type: "jpeg", quality: 0.98 },
            html2canvas: { scale: 2, backgroundColor: "#0f1614" },
            jsPDF: { unit: "in", format: "letter", orientation: "portrait" },
        };
        html2pdf().set(opt).from(compareResult).save();
    });

    async function triggerScrape(mockUnhealthy = false) {
        demoLogBox.classList.remove("hidden");
        setTimelineFromPhase("scrape", false);
        demoLogBox.textContent = mockUnhealthy
            ? "Starting demo break: empty extract → health FAIL → real bdata heal…"
            : "Starting healthy Studio scrape…";

        try {
            const res = await fetch("/api/trigger-scrape", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mock_unhealthy: mockUnhealthy }),
            });
            const body = await res.json().catch(() => ({}));
            if (res.ok) {
                demoLogBox.textContent =
                    `Pipeline started\ncollector: ${body.collector_id || "?"}\n` +
                    (mockUnhealthy
                        ? "mode: inject empty extract (demo) + real heal CLI"
                        : "mode: healthy Studio run");
                startHealPolling();
            } else {
                demoLogBox.textContent = "Failed to trigger pipeline.";
                setTimelineFromPhase("error", false);
            }
        } catch (err) {
            demoLogBox.textContent = `Error: ${err.message}`;
            setTimelineFromPhase("error", false);
        }
    }

    btnRunHealthy.addEventListener("click", () => triggerScrape(false));
    btnTriggerHeal.addEventListener("click", () => triggerScrape(true));
});

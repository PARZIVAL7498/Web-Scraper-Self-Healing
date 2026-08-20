document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();

    let chartInstance = null;
    let currentComparisonData = null;

    // Elements
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

    const btnExportPdf = document.getElementById("btn-export-pdf");
    const btnExportMd = document.getElementById("btn-export-md");

    const btnRunHealthy = document.getElementById("btn-run-healthy");
    const btnTriggerHeal = document.getElementById("btn-trigger-heal");
    const demoLogBox = document.getElementById("demo-log");

    // Tab Switching Logic
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

    // Update input placeholder on target URL change
    chatUrlInput.addEventListener("input", () => {
        const val = chatUrlInput.value.trim();
        if (val) {
            userInput.placeholder = `Ask a question about ${val}...`;
        }
    });

    // Fetch Pipeline Status
    async function fetchStatus() {
        try {
            const res = await fetch("/api/status");
            if (res.ok) {
                const data = await res.json();
                document.getElementById("chunks-count").textContent = data.indexed_chunks;
                document.getElementById("pages-count").textContent = data.baseline_pages;
                document.getElementById("llm-badge").textContent = data.llm_provider;

                const statusDot = document.getElementById("status-dot");
                const statusText = document.getElementById("status-text");

                if (data.indexed_chunks > 0) {
                    statusDot.className = "status-dot green";
                    statusText.textContent = `Indexed & Ready (${data.indexed_chunks} chunks)`;
                } else {
                    statusDot.className = "status-dot yellow";
                    statusText.textContent = "Vector DB Empty — Run Scrape";
                }
            }
        } catch (err) {
            console.error("Failed to fetch status", err);
        }
    }

    // Chat submit handler with Target URL
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
                body: JSON.stringify({ query: query, url: targetUrl })
            });

            removeMessage(loadingId);

            if (res.ok) {
                const data = await res.json();
                appendMessage("assistant", data.answer, data.citations);
            } else {
                const errData = await res.json();
                appendMessage("assistant", `⚠️ Error: ${errData.detail || "Failed to process chat query"}`);
            }
        } catch (err) {
            removeMessage(loadingId);
            appendMessage("assistant", `⚠️ Network error: ${err.message}`);
        } finally {
            sendBtn.disabled = false;
            fetchStatus();
        }
    });

    // Render Clean Assistant Messages using Marked.js
    function appendMessage(role, text, citations = []) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}-message`;

        const avatarDiv = document.createElement("div");
        avatarDiv.className = "avatar";
        avatarDiv.textContent = role === "user" ? "👤" : "🤖";

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
            title.textContent = "Source Citations";
            citationsBox.appendChild(title);

            const list = document.createElement("div");
            list.className = "citations-list";

            citations.forEach(cit => {
                const a = document.createElement("a");
                a.className = "citation-pill";
                a.href = cit.url;
                a.target = "_blank";
                a.innerHTML = `📄 [${cit.id}] ${cit.title}`;
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
        avatarDiv.className = "avatar";
        avatarDiv.textContent = "🤖";

        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";
        contentDiv.innerHTML = `<p>🌐 Live Web Scraping & Indexing <b>${targetUrl}</b>... (1.5 - 3s network crawl)</p>`;

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

    // Render Radar Chart using Chart.js
    function renderComparisonChart(compA, compB, scoresA, scoresB) {
        const ctx = document.getElementById("comparison-chart").getContext("2d");
        
        if (chartInstance) {
            chartInstance.destroy();
        }

        chartInstance = new Chart(ctx, {
            type: "radar",
            data: {
                labels: [
                    "Performance & Speed",
                    "Ease of Local Setup",
                    "Distributed Scaling",
                    "Feature Completeness",
                    "Ecosystem Support"
                ],
                datasets: [
                    {
                        label: compA,
                        data: scoresA || [95, 95, 45, 88, 90],
                        fill: true,
                        backgroundColor: "rgba(59, 130, 246, 0.25)",
                        borderColor: "#3b82f6",
                        pointBackgroundColor: "#3b82f6",
                        pointBorderColor: "#fff",
                        pointHoverBackgroundColor: "#fff",
                        pointHoverBorderColor: "#3b82f6"
                    },
                    {
                        label: compB,
                        data: scoresB || [92, 55, 98, 92, 88],
                        fill: true,
                        backgroundColor: "rgba(139, 92, 246, 0.25)",
                        borderColor: "#8b5cf6",
                        pointBackgroundColor: "#8b5cf6",
                        pointBorderColor: "#fff",
                        pointHoverBackgroundColor: "#fff",
                        pointHoverBorderColor: "#8b5cf6"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        angleLines: { color: "rgba(255, 255, 255, 0.15)" },
                        grid: { color: "rgba(255, 255, 255, 0.1)" },
                        pointLabels: {
                            color: "#94a3b8",
                            font: { family: "Outfit", size: 11, weight: "500" }
                        },
                        ticks: {
                            display: false,
                            min: 0,
                            max: 100
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: "#f8fafc",
                            font: { family: "Outfit", size: 12, weight: "600" }
                        }
                    }
                }
            }
        });
    }

    // Compare Form Handler
    compareForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const urlA = urlAInput.value.trim();
        const urlB = urlBInput.value.trim();
        const topic = topicInput.value.trim();

        if (!urlA || !urlB || !topic) return;

        compareProgress.classList.remove("hidden");
        compareResult.classList.add("hidden");
        resetProgressSteps();

        setStepStatus(1, "active");

        setTimeout(() => setStepStatus(1, "done"), 800);
        setTimeout(() => setStepStatus(2, "active"), 900);
        setTimeout(() => setStepStatus(2, "done"), 1600);
        setTimeout(() => setStepStatus(3, "active"), 1700);

        try {
            const res = await fetch("/api/scrape-and-compare", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url_a: urlA, url_b: urlB, topic: topic })
            });

            setStepStatus(3, "done");
            setStepStatus(4, "active");

            if (res.ok) {
                const data = await res.json();
                currentComparisonData = data;
                setStepStatus(4, "done");

                if (window.marked) {
                    resultMarkdown.innerHTML = marked.parse(data.comparison_markdown);
                } else {
                    resultMarkdown.innerText = data.comparison_markdown;
                }

                renderComparisonChart(data.competitor_a, data.competitor_b, data.scores_a, data.scores_b);

                if (data.citations && data.citations.length > 0) {
                    compareCitations.innerHTML = `
                        <div class="citations-title">Verified Source Documentation Citations</div>
                        <div class="citations-list">
                            ${data.citations.map(c => `
                                <a href="${c.url}" target="_blank" class="citation-pill">
                                    📄 [${c.id}] ${c.title}
                                </a>
                            `).join("")}
                        </div>
                    `;
                } else {
                    compareCitations.innerHTML = "";
                }

                compareResult.classList.remove("hidden");
                fetchStatus();
            } else {
                const errData = await res.json();
                alert(`Error comparing documentation: ${errData.detail || "Failed"}`);
            }
        } catch (err) {
            alert(`Network Error: ${err.message}`);
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

    // Export Markdown Report Handler
    btnExportMd.addEventListener("click", () => {
        if (!currentComparisonData) return;
        
        let mdContent = `# ⚡ Competitive Documentation Report: ${currentComparisonData.competitor_a} vs ${currentComparisonData.competitor_b}\n\n`;
        mdContent += `**Topic**: ${currentComparisonData.topic}\n\n`;
        mdContent += currentComparisonData.comparison_markdown + "\n\n";
        mdContent += `## 📄 Source Documentation Citations\n`;
        currentComparisonData.citations.forEach(c => {
            mdContent += `- [${c.title}](${c.url})\n`;
        });

        const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `Doc_Comparison_${currentComparisonData.competitor_a}_vs_${currentComparisonData.competitor_b}.md`;
        link.click();
    });

    // Export PDF Report Handler
    btnExportPdf.addEventListener("click", () => {
        if (!currentComparisonData || !window.html2pdf) return;

        const opt = {
            margin: 0.5,
            filename: `Doc_Comparison_${currentComparisonData.competitor_a}_vs_${currentComparisonData.competitor_b}.pdf`,
            image: { type: "jpeg", quality: 0.98 },
            html2canvas: { scale: 2, backgroundColor: "#0b0f19" },
            jsPDF: { unit: "in", format: "letter", orientation: "portrait" }
        };

        html2pdf().set(opt).from(compareResult).save();
    });

    // Demo control handlers
    async function triggerScrape(mockUnhealthy = false) {
        demoLogBox.classList.remove("hidden");
        demoLogBox.innerHTML = `⏳ Triggering pipeline (mock_unhealthy=${mockUnhealthy})...<br>`;

        try {
            const res = await fetch("/api/trigger-scrape", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mock_unhealthy: mockUnhealthy })
            });

            if (res.ok) {
                demoLogBox.innerHTML += `🚀 Background process started!<br>Check terminal console to see <code>bdata scraper heal</code> logs.`;
                setTimeout(fetchStatus, 3000);
            } else {
                demoLogBox.innerHTML += `❌ Failed to trigger pipeline.`;
            }
        } catch (err) {
            demoLogBox.innerHTML += `❌ Error: ${err.message}`;
        }
    }

    btnRunHealthy.addEventListener("click", () => triggerScrape(false));
    btnTriggerHeal.addEventListener("click", () => triggerScrape(true));
});

/**
 * AI PERSONAL EXAMINER - CLIENT ENGINE
 * Handles API communication, session memory, UI state, Voice Mode, Code Sandbox,
 * Interview Countdown Timer, History Filters, Keyboard Shortcuts, and Report Exporting.
 */

// Smart API endpoint discovery (fallback to localhost:8000 if served via Live Server or file)
const API_BASE = (() => {
  if (
    window.location.protocol === "file:" ||
    window.location.port === "5500" ||
    window.location.port === "3000" ||
    !window.location.origin ||
    window.location.origin === "null"
  ) {
    return "http://localhost:8000";
  }
  return window.location.origin;
})();

// Session Helpers
const Session = {
  getUser: () => ({
    id: localStorage.getItem("examiner_user_id"),
    name: localStorage.getItem("examiner_user_name") || "Learner",
    topic: localStorage.getItem("examiner_topic") || "Python",
    difficulty: localStorage.getItem("examiner_difficulty") || "easy"
  }),
  setUser: (id, name, topic, difficulty) => {
    localStorage.setItem("examiner_user_id", id);
    localStorage.setItem("examiner_user_name", name);
    localStorage.setItem("examiner_topic", topic);
    localStorage.setItem("examiner_difficulty", difficulty);
  },
  clear: () => {
    localStorage.removeItem("examiner_user_id");
    localStorage.removeItem("examiner_user_name");
    localStorage.removeItem("examiner_topic");
    localStorage.removeItem("examiner_difficulty");
  }
};

// Helper: Setup user initials avatar in navbars
function setupUserAvatar(name) {
  const navBadge = document.getElementById("user-nav-name");
  const avatar = document.getElementById("user-avatar-initial");
  if (navBadge) navBadge.textContent = name || "Learner";
  if (avatar) avatar.textContent = (name || "U").charAt(0).toUpperCase();
}

// =========================================================================
// 1. HOME PAGE INITIALIZATION
// =========================================================================
function initHomePage() {
  const form = document.getElementById("start-exam-form");
  const nameInput = document.getElementById("learner-name");
  const topicSelect = document.getElementById("exam-topic");
  const diffSelect = document.getElementById("exam-difficulty");
  const returnBanner = document.getElementById("returning-user-banner");
  const bannerAvatar = document.getElementById("banner-avatar");

  const savedUser = Session.getUser();
  if (savedUser.id && nameInput) {
    nameInput.value = savedUser.name;
    if (savedUser.topic && topicSelect) topicSelect.value = savedUser.topic;
    if (savedUser.difficulty && diffSelect) diffSelect.value = savedUser.difficulty;
    if (returnBanner) {
      returnBanner.style.display = "flex";
      document.getElementById("saved-learner-name").textContent = savedUser.name;
      if (bannerAvatar) bannerAvatar.textContent = savedUser.name.charAt(0).toUpperCase();
    }
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submitBtn = form.querySelector("button[type='submit']");
      const originalText = submitBtn.innerHTML;
      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <div class="spinner" style="width: 18px; height: 18px; border-width: 2px; margin: 0;"></div>
        <span>Starting Exam...</span>
      `;

      try {
        const payload = {
          name: nameInput.value.trim(),
          topic: topicSelect.value,
          difficulty: diffSelect.value
        };

        const res = await fetch(`${API_BASE}/exam/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("Could not start exam session.");

        const data = await res.json();
        Session.setUser(data.user_id, data.name, data.topic, data.current_difficulty);
        window.location.href = "/exam";
      } catch (err) {
        alert(`Error: ${err.message}`);
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    });
  }
}

// =========================================================================
// 2. EXAM PAGE INITIALIZATION (Voice, Code Sandbox & Timer)
// =========================================================================
let currentQuestionId = null;
let currentQuestionText = "";
let isSpeaking = false;
let isRecording = false;
let speechRecognizer = null;
let timerInterval = null;
let timeRemaining = 180; // 3 minutes default
let timerIsPaused = false;

// --- Timer Engine ---
function startTimer(seconds = 180) {
  clearInterval(timerInterval);
  timeRemaining = seconds;
  timerIsPaused = false;
  updateTimerUI();

  timerInterval = setInterval(() => {
    if (!timerIsPaused) {
      timeRemaining--;
      updateTimerUI();
      if (timeRemaining <= 0) {
        clearInterval(timerInterval);
        const pill = document.getElementById("exam-timer-pill");
        if (pill) pill.classList.add("timer-warning");
      }
    }
  }, 1000);
}

function updateTimerUI() {
  const display = document.getElementById("timer-display");
  const pill = document.getElementById("exam-timer-pill");
  if (!display) return;

  const mins = Math.floor(Math.max(0, timeRemaining) / 60);
  const secs = Math.max(0, timeRemaining) % 60;
  display.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;

  if (pill) {
    if (timeRemaining <= 30) {
      pill.classList.add("timer-warning");
    } else {
      pill.classList.remove("timer-warning");
    }
  }
}

// --- Voice Examiner TTS ---
const SPEAKER_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>`;
const STOP_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;

function toggleExaminerVoice() {
  if (!("speechSynthesis" in window)) {
    alert("Speech Synthesis is not supported in this browser.");
    return;
  }

  const icon = document.getElementById("voice-btn-icon");
  const label = document.getElementById("voice-btn-label");
  const soundwave = document.getElementById("soundwave-box");

  if (isSpeaking) {
    window.speechSynthesis.cancel();
    isSpeaking = false;
    if (icon) icon.innerHTML = SPEAKER_SVG;
    if (label) label.textContent = "Listen to Examiner";
    if (soundwave) soundwave.classList.remove("is-speaking");
    return;
  }

  if (!currentQuestionText) return;

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(currentQuestionText);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  // Pick a natural English voice if available
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice = voices.find(v => v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Samantha") || v.name.includes("Daniel")));
  if (preferredVoice) utterance.voice = preferredVoice;

  utterance.onstart = () => {
    isSpeaking = true;
    if (icon) icon.innerHTML = STOP_SVG;
    if (label) label.textContent = "Stop Examiner";
    if (soundwave) soundwave.classList.add("is-speaking");
  };

  utterance.onend = () => {
    isSpeaking = false;
    if (icon) icon.innerHTML = SPEAKER_SVG;
    if (label) label.textContent = "Listen to Examiner";
    if (soundwave) soundwave.classList.remove("is-speaking");
  };

  utterance.onerror = () => {
    isSpeaking = false;
    if (icon) icon.innerHTML = SPEAKER_SVG;
    if (label) label.textContent = "Listen to Examiner";
    if (soundwave) soundwave.classList.remove("is-speaking");
  };

  window.speechSynthesis.speak(utterance);
}

// --- Voice Dictation STT ---
function toggleDictation() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Voice dictation is not supported in this browser. Please use Chrome, Edge, or Safari.");
    return;
  }

  const dictateBtn = document.getElementById("dictate-btn");
  const micIcon = document.getElementById("mic-icon");
  const micText = document.getElementById("mic-text");
  const answerInput = document.getElementById("answer-input");

  if (isRecording && speechRecognizer) {
    speechRecognizer.stop();
    return;
  }

  speechRecognizer = new SpeechRecognition();
  speechRecognizer.continuous = true;
  speechRecognizer.interimResults = true;
  speechRecognizer.lang = "en-US";

  speechRecognizer.onstart = () => {
    isRecording = true;
    if (dictateBtn) dictateBtn.classList.add("is-recording");
    if (micIcon) micIcon.textContent = "🔴";
    if (micText) micText.textContent = "Listening...";
  };

  speechRecognizer.onresult = (event) => {
    let interim = "";
    let final = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        final += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    if (final && answerInput) {
      answerInput.value += (answerInput.value ? " " : "") + final.trim();
      updateWordCount();
    }
  };

  speechRecognizer.onerror = (e) => {
    console.warn("Speech recognition error:", e);
    stopDictationUI();
  };

  speechRecognizer.onend = () => {
    stopDictationUI();
  };

  speechRecognizer.start();
}

function stopDictationUI() {
  isRecording = false;
  const dictateBtn = document.getElementById("dictate-btn");
  const micIcon = document.getElementById("mic-icon");
  const micText = document.getElementById("mic-text");
  if (dictateBtn) dictateBtn.classList.remove("is-recording");
  if (micIcon) micIcon.textContent = "🎙️";
  if (micText) micText.textContent = "Dictate Answer";
}

function updateWordCount() {
  const input = document.getElementById("answer-input");
  const badge = document.getElementById("word-count-badge");
  if (!input || !badge) return;
  const words = input.value.trim().split(/\s+/).filter(Boolean).length;
  badge.textContent = `${words} word${words === 1 ? "" : "s"}`;
}

async function loadNextQuestion() {
  const user = Session.getUser();
  if (!user.id) {
    window.location.href = "/";
    return;
  }

  // Stop any ongoing speech
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  isSpeaking = false;

  const container = document.getElementById("exam-interface");
  const loading = document.getElementById("exam-loading");
  const evalPanel = document.getElementById("evaluation-panel");
  const answerInput = document.getElementById("answer-input");
  const codeInput = document.getElementById("code-input");
  const submitBtn = document.getElementById("submit-answer-btn");

  if (container) container.style.display = "none";
  if (evalPanel) evalPanel.style.display = "none";
  if (loading) loading.style.display = "block";
  if (answerInput) {
    answerInput.value = "";
    answerInput.disabled = false;
  }
  if (codeInput) {
    codeInput.value = "";
    codeInput.disabled = false;
  }
  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.style.display = "inline-flex";
    submitBtn.innerHTML = `
      <span>Submit Answer</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
    `;
  }

  updateWordCount();

  try {
    const res = await fetch(`${API_BASE}/exam/question`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: parseInt(user.id),
        topic: user.topic,
        difficulty: user.difficulty
      })
    });

    if (!res.ok) throw new Error("Failed to generate personalized question.");

    const q = await res.json();
    currentQuestionId = q.id;
    currentQuestionText = q.question_text;

    // Update UI elements
    document.getElementById("topic-pill").textContent = q.topic;
    document.getElementById("q-number-pill").textContent = `Question #${q.question_number}`;
    document.getElementById("concept-pill").textContent = `Concept: ${q.concept}`;
    
    const diffBadge = document.getElementById("difficulty-badge");
    diffBadge.textContent = q.difficulty.toUpperCase();
    diffBadge.className = `diff-badge diff-${q.difficulty.toLowerCase()}`;

    document.getElementById("question-text-box").textContent = q.question_text;

    // Code Sandbox Header update
    const codeHeader = document.getElementById("code-lang-label");
    if (codeHeader) codeHeader.textContent = `${q.topic} Code Implementation`;

    if (loading) loading.style.display = "none";
    if (container) container.style.display = "block";

    // Start fresh 3-minute interview timer
    startTimer(180);

    // Reset voice button state
    const icon = document.getElementById("voice-btn-icon");
    const label = document.getElementById("voice-btn-label");
    const soundwave = document.getElementById("soundwave-box");
    if (icon) icon.innerHTML = SPEAKER_SVG;
    if (label) label.textContent = "Listen to Examiner";
    if (soundwave) soundwave.classList.remove("is-speaking");

    // Auto-focus input
    if (answerInput) answerInput.focus();

  } catch (err) {
    if (loading) loading.innerHTML = `<p style="color: var(--accent-rose); font-weight: 600;">Error: ${err.message}</p><a href="/" class="btn btn-secondary" style="margin-top:16px;">Back to Home</a>`;
  }
}

function initExamPage() {
  const user = Session.getUser();
  if (!user.id) {
    window.location.href = "/";
    return;
  }

  setupUserAvatar(user.name);

  const answerForm = document.getElementById("answer-form");
  const answerInput = document.getElementById("answer-input");
  const codeInput = document.getElementById("code-input");
  const nextQBtn = document.getElementById("next-question-btn");
  const finishBtn = document.getElementById("finish-exam-btn");
  const voiceBtn = document.getElementById("voice-speak-btn");
  const dictateBtn = document.getElementById("dictate-btn");

  const tabText = document.getElementById("tab-text-mode");
  const tabCode = document.getElementById("tab-code-mode");
  const textModeBox = document.getElementById("text-mode-container");
  const codeModeBox = document.getElementById("code-mode-container");

  const timerToggle = document.getElementById("timer-toggle-btn");
  const timerReset = document.getElementById("timer-reset-btn");

  // Voice Examiner listener
  if (voiceBtn) {
    voiceBtn.addEventListener("click", toggleExaminerVoice);
  }

  // Dictation listener
  if (dictateBtn) {
    dictateBtn.addEventListener("click", toggleDictation);
  }

  // Word count listener
  if (answerInput) {
    answerInput.addEventListener("input", updateWordCount);
  }

  // Keyboard shortcut: Ctrl+Enter (or Cmd+Enter) to submit answer
  [answerInput, codeInput].forEach(inp => {
    if (inp) {
      inp.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          if (answerForm) answerForm.requestSubmit();
        }
      });
    }
  });

  // Code editor Tab key indentation
  if (codeInput) {
    codeInput.addEventListener("keydown", (e) => {
      if (e.key === "Tab") {
        e.preventDefault();
        const start = codeInput.selectionStart;
        const end = codeInput.selectionEnd;
        codeInput.value = codeInput.value.substring(0, start) + "    " + codeInput.value.substring(end);
        codeInput.selectionStart = codeInput.selectionEnd = start + 4;
      }
    });
  }

  // Code Sandbox Runner, Template, and Console controls
  const runCodeBtn = document.getElementById("run-code-btn");
  const clearConsoleBtn = document.getElementById("clear-console-btn");
  const insertTemplateBtn = document.getElementById("insert-template-btn");
  const terminalOutput = document.getElementById("sandbox-terminal-output");
  const terminalBadge = document.getElementById("terminal-status-badge");

  if (insertTemplateBtn && codeInput) {
    insertTemplateBtn.addEventListener("click", () => {
      const topicLower = (user.topic || "").toLowerCase();
      if (topicLower.includes("javascript") || topicLower.includes("js")) {
        codeInput.value = `// JavaScript Implementation\nfunction solution() {\n    console.log("Running technical solution...");\n    return true;\n}\n\nsolution();\n`;
      } else {
        codeInput.value = `# Python 3 Implementation\ndef solution():\n    print("Executing solution in sandbox...")\n    return True\n\nif __name__ == "__main__":\n    res = solution()\n    print("Output:", res)\n`;
      }
      codeInput.focus();
    });
  }

  if (clearConsoleBtn && terminalOutput) {
    clearConsoleBtn.addEventListener("click", () => {
      terminalOutput.innerHTML = `<span class="terminal-dim">// Console cleared. Ready to execute code.</span>`;
      if (terminalBadge) {
        terminalBadge.className = "terminal-badge ready";
        terminalBadge.textContent = "Ready";
      }
    });
  }

  if (runCodeBtn && codeInput && terminalOutput) {
    runCodeBtn.addEventListener("click", async () => {
      const code = codeInput.value.trim();
      if (!code) {
        terminalOutput.innerHTML = `<span class="terminal-stderr">Error: No code written in the sandbox editor to execute.</span>`;
        return;
      }

      const runIcon = document.getElementById("run-btn-icon");
      const runLabel = document.getElementById("run-btn-label");
      runCodeBtn.disabled = true;
      if (runIcon) runIcon.textContent = "⏳";
      if (runLabel) runLabel.textContent = "Executing...";

      if (terminalBadge) {
        terminalBadge.className = "terminal-badge running";
        terminalBadge.textContent = "Running...";
      }

      terminalOutput.innerHTML = `<span class="terminal-dim">// Spawning isolated sandbox subprocess...</span>\n`;

      const topicLower = (user.topic || "").toLowerCase();
      const lang = (topicLower.includes("javascript") || topicLower.includes("js")) ? "javascript" : "python";

      try {
        const res = await fetch(`${API_BASE}/exam/run-code`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: code,
            language: lang,
            timeout_seconds: 4.0
          })
        });

        if (!res.ok) {
          throw new Error(`HTTP error ${res.status}`);
        }

        const data = await res.json();
        terminalOutput.innerHTML = "";

        if (data.stdout) {
          const stdoutSpan = document.createElement("span");
          stdoutSpan.className = "terminal-stdout";
          stdoutSpan.textContent = data.stdout;
          terminalOutput.appendChild(stdoutSpan);
        }

        if (data.stderr) {
          const stderrSpan = document.createElement("span");
          stderrSpan.className = "terminal-stderr";
          stderrSpan.textContent = (data.stdout ? "\n" : "") + data.stderr;
          terminalOutput.appendChild(stderrSpan);
        }

        if (!data.stdout && !data.stderr) {
          terminalOutput.innerHTML = `<span class="terminal-dim">// Execution completed with no console output (exit code 0).</span>`;
        }

        if (terminalBadge) {
          if (data.success) {
            terminalBadge.className = "terminal-badge success";
            terminalBadge.textContent = `Exit: 0 (${data.execution_time_ms}ms)`;
          } else if (data.error && data.error.includes("Timeout")) {
            terminalBadge.className = "terminal-badge error";
            terminalBadge.textContent = "Timeout (4s)";
          } else {
            terminalBadge.className = "terminal-badge error";
            terminalBadge.textContent = `Exit: ${data.exit_code} (${data.execution_time_ms}ms)`;
          }
        }
      } catch (err) {
        terminalOutput.innerHTML = `<span class="terminal-stderr">Sandbox execution error: ${err.message}</span>`;
        if (terminalBadge) {
          terminalBadge.className = "terminal-badge error";
          terminalBadge.textContent = "Failed";
        }
      } finally {
        runCodeBtn.disabled = false;
        if (runIcon) runIcon.textContent = "▶";
        if (runLabel) runLabel.textContent = "Run Code";
      }
    });
  }

  // Mode Tabs Switching
  if (tabText && tabCode) {
    tabText.addEventListener("click", () => {
      tabText.classList.add("active");
      tabCode.classList.remove("active");
      if (textModeBox) textModeBox.style.display = "block";
      if (codeModeBox) codeModeBox.style.display = "none";
      if (answerInput) answerInput.focus();
    });

    tabCode.addEventListener("click", () => {
      tabCode.classList.add("active");
      tabText.classList.remove("active");
      if (codeModeBox) codeModeBox.style.display = "block";
      if (codeInput) codeInput.focus();
    });
  }

  // Timer controls
  if (timerToggle) {
    timerToggle.addEventListener("click", () => {
      timerIsPaused = !timerIsPaused;
      timerToggle.textContent = timerIsPaused ? "▶" : "⏸";
    });
  }

  if (timerReset) {
    timerReset.addEventListener("click", () => {
      startTimer(180);
    });
  }

  // Form submission
  if (answerForm) {
    answerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById("submit-answer-btn");
      const evalPanel = document.getElementById("evaluation-panel");

      let finalAnswer = answerInput ? answerInput.value.trim() : "";
      const codeSnippet = codeInput ? codeInput.value.trim() : "";

      if (codeSnippet) {
        finalAnswer += `\n\n[Code Implementation]:\n\`\`\`\n${codeSnippet}\n\`\`\``;
        if (terminalOutput && terminalOutput.textContent && !terminalOutput.textContent.includes("// Click \"▶ Run Code\"")) {
          const runOut = terminalOutput.textContent.trim();
          if (runOut && runOut.length < 500) {
            finalAnswer += `\n\n[Sandbox Execution Output]:\n\`\`\`\n${runOut}\n\`\`\``;
          }
        }
      }

      if (!finalAnswer) return;

      clearInterval(timerInterval);
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      isSpeaking = false;
      stopDictationUI();

      submitBtn.disabled = true;
      submitBtn.innerHTML = `
        <div class="spinner" style="width: 18px; height: 18px; border-width: 2px; margin: 0;"></div>
        <span>Evaluating Answer...</span>
      `;
      if (answerInput) answerInput.disabled = true;
      if (codeInput) codeInput.disabled = true;

      try {
        const res = await fetch(`${API_BASE}/exam/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: parseInt(user.id),
            question_id: currentQuestionId,
            answer_text: finalAnswer
          })
        });

        if (!res.ok) throw new Error("Evaluation failed.");

        const evalData = await res.json();

        // Update Session difficulty if changed
        if (evalData.recommended_difficulty) {
          Session.setUser(user.id, user.name, user.topic, evalData.recommended_difficulty);
        }

        // Render evaluation results
        document.getElementById("eval-score-num").textContent = evalData.score;
        document.getElementById("eval-rec-diff").textContent = evalData.recommended_difficulty.toUpperCase();
        document.getElementById("eval-feedback-text").textContent = evalData.feedback;

        // Render correct points
        const correctList = document.getElementById("eval-correct-list");
        correctList.innerHTML = "";
        (evalData.correct_points || []).forEach(pt => {
          const li = document.createElement("li");
          li.textContent = pt;
          correctList.appendChild(li);
        });

        // Render missing points
        const missingList = document.getElementById("eval-missing-list");
        missingList.innerHTML = "";
        (evalData.missing_points || []).forEach(pt => {
          const li = document.createElement("li");
          li.textContent = pt;
          missingList.appendChild(li);
        });

        // Mastery alert
        const masteryAlert = document.getElementById("concept-mastered-badge");
        if (masteryAlert) {
          masteryAlert.style.display = evalData.concept_mastered ? "inline-flex" : "none";
        }

        submitBtn.style.display = "none";
        if (evalPanel) {
          evalPanel.style.display = "block";
          evalPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (err) {
        alert(`Error: ${err.message}`);
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
          <span>Submit Answer</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        `;
        if (answerInput) answerInput.disabled = false;
        if (codeInput) codeInput.disabled = false;
      }
    });
  }

  if (nextQBtn) {
    nextQBtn.addEventListener("click", () => {
      loadNextQuestion();
    });
  }

  if (finishBtn) {
    finishBtn.addEventListener("click", () => {
      window.location.href = "/result";
    });
  }

  loadNextQuestion();
}

// =========================================================================
// 3. DASHBOARD PAGE INITIALIZATION (Reset Memory & Topic Filtering)
// =========================================================================
async function initDashboardPage() {
  const user = Session.getUser();
  if (!user.id) {
    window.location.href = "/";
    return;
  }

  setupUserAvatar(user.name);

  try {
    const [analysisRes, historyRes] = await Promise.all([
      fetch(`${API_BASE}/exam/analysis/${user.id}`),
      fetch(`${API_BASE}/exam/history/${user.id}`)
    ]);

    if (!analysisRes.ok) throw new Error("Failed to load learner progress.");

    const analysis = await analysisRes.json();
    const history = historyRes.ok ? await historyRes.json() : [];

    // Header stats
    document.getElementById("dash-total-q").textContent = analysis.total_questions;
    document.getElementById("dash-avg-score").textContent = `${analysis.overall_average_score}/10`;
    document.getElementById("dash-curr-diff").textContent = analysis.current_difficulty.toUpperCase();
    document.getElementById("dash-avoided-count").textContent = analysis.questions_avoided;

    // Strongest & Weakest topics
    document.getElementById("dash-strongest-topic").textContent = analysis.strongest_topic || "Assessing...";
    document.getElementById("dash-weakest-topic").textContent = analysis.weakest_topic || "None identified";

    // Mastered concepts chips
    const masteredContainer = document.getElementById("dash-mastered-chips");
    masteredContainer.innerHTML = "";
    if (analysis.mastered_concepts && analysis.mastered_concepts.length > 0) {
      analysis.mastered_concepts.forEach(c => {
        const chip = document.createElement("span");
        chip.className = "chip chip-mastered";
        chip.innerHTML = `✓ ${c}`;
        masteredContainer.appendChild(chip);
      });
    } else {
      masteredContainer.innerHTML = `<span style="color: var(--text-dim); font-size: 13px;">Score 8+ on concepts to master them.</span>`;
    }

    // Topic progress bars & Reset options
    const topicsContainer = document.getElementById("topic-bars-container");
    const resetTopicSelect = document.getElementById("reset-topic-select");
    const historyFilter = document.getElementById("history-topic-filter");

    topicsContainer.innerHTML = "";
    if (resetTopicSelect) {
      resetTopicSelect.innerHTML = `<option value="all">Entire Profile (All Topics & History)</option>`;
    }
    if (historyFilter) {
      historyFilter.innerHTML = `<option value="all" selected>All Domains</option>`;
    }

    (analysis.topic_breakdown || []).forEach(tb => {
      const pct = Math.min(100, Math.round((tb.average_score / 10) * 100));
      const row = document.createElement("div");
      row.className = "topic-progress-row";
      row.innerHTML = `
        <div class="topic-info-bar">
          <span>${tb.topic} (${tb.questions_attempted} Qs)</span>
          <span>${tb.average_score}/10 (${pct}%)</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${pct}%"></div>
        </div>
      `;
      topicsContainer.appendChild(row);

      if (resetTopicSelect) {
        const opt = document.createElement("option");
        opt.value = tb.topic;
        opt.textContent = `Topic: ${tb.topic} (${tb.questions_attempted} questions)`;
        resetTopicSelect.appendChild(opt);
      }

      if (historyFilter) {
        const opt = document.createElement("option");
        opt.value = tb.topic.toLowerCase();
        opt.textContent = tb.topic;
        historyFilter.appendChild(opt);
      }
    });

    // Render Chronological History Log
    function renderHistory(items) {
      const historyContainer = document.getElementById("history-items-container");
      historyContainer.innerHTML = "";
      if (items.length === 0) {
        historyContainer.innerHTML = `<p style="color: var(--text-dim); padding: 18px 0; text-align: center;">No question history recorded for this view.</p>`;
        return;
      }
      items.forEach(item => {
        const div = document.createElement("div");
        div.className = "history-card";
        div.dataset.topic = (item.topic || "").toLowerCase();
        div.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; gap: 8px; align-items: center;">
              <span class="topic-badge">${item.topic}</span>
              <span class="diff-badge diff-${item.difficulty.toLowerCase()}">${item.difficulty}</span>
              <span class="q-concept">${item.concept}</span>
            </div>
            <div style="font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: ${item.score >= 8 ? 'var(--success-text)' : item.score >= 5 ? 'var(--warning-text)' : 'var(--danger-text)'};">
              Score: ${item.score}/10
            </div>
          </div>
          <p style="font-size: 14.5px; font-weight: 600; color: var(--text-main); margin-bottom: 10px; line-height: 1.5;">${item.question_text}</p>
          <div style="font-size: 13px; color: var(--text-secondary); background: var(--bg-subtle); border: 1px solid var(--border-color); padding: 10px 14px; border-radius: var(--radius-sm); font-family: var(--font-mono); margin-bottom: 10px; white-space: pre-wrap; line-height: 1.5;">${item.answer_text}</div>
          <div style="display: flex; align-items: flex-start; gap: 8px; font-size: 13px; color: var(--text-secondary); line-height: 1.5;">
            <span style="font-weight: 600; color: var(--primary);">Feedback:</span>
            <span>${item.feedback}</span>
          </div>
        `;
        historyContainer.appendChild(div);
      });
    }

    renderHistory(history);

    // Topic Filter Listener
    if (historyFilter) {
      historyFilter.addEventListener("change", (e) => {
        const sel = e.target.value;
        if (sel === "all") {
          renderHistory(history);
        } else {
          const filtered = history.filter(h => (h.topic || "").toLowerCase() === sel);
          renderHistory(filtered);
        }
      });
    }

    // Modal Handlers
    const resetModal = document.getElementById("reset-memory-modal");
    const openResetBtn = document.getElementById("open-reset-modal-btn");
    const cancelResetBtn = document.getElementById("cancel-reset-btn");
    const confirmResetBtn = document.getElementById("confirm-reset-btn");

    if (openResetBtn && resetModal) {
      openResetBtn.addEventListener("click", () => {
        resetModal.style.display = "flex";
      });
    }

    if (cancelResetBtn && resetModal) {
      cancelResetBtn.addEventListener("click", () => {
        resetModal.style.display = "none";
      });
    }

    if (confirmResetBtn) {
      confirmResetBtn.addEventListener("click", async () => {
        const selectedTopic = resetTopicSelect ? resetTopicSelect.value : "all";
        confirmResetBtn.disabled = true;
        confirmResetBtn.textContent = "Resetting...";

        try {
          const res = await fetch(`${API_BASE}/exam/reset`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: parseInt(user.id),
              topic: selectedTopic === "all" ? null : selectedTopic
            })
          });

          if (!res.ok) throw new Error("Reset failed.");
          window.location.reload();
        } catch (err) {
          alert(`Error: ${err.message}`);
          confirmResetBtn.disabled = false;
          confirmResetBtn.textContent = "Confirm Reset";
        }
      });
    }

  } catch (err) {
    console.error(err);
  }
}

// =========================================================================
// 4. RESULT SCREEN INITIALIZATION ("What My Examiner Learned About Me")
// =========================================================================
async function initResultPage() {
  const user = Session.getUser();
  if (!user.id) {
    window.location.href = "/";
    return;
  }

  setupUserAvatar(user.name);

  try {
    const res = await fetch(`${API_BASE}/exam/analysis/${user.id}`);
    if (!res.ok) throw new Error("Failed to load personalized report.");

    const data = await res.json();

    // AI Observation
    document.getElementById("wow-ai-observation").textContent = data.ai_observation;

    // Verified Strengths
    const strengthContainer = document.getElementById("wow-strengths-list");
    strengthContainer.innerHTML = "";
    if (data.strengths && data.strengths.length > 0) {
      data.strengths.forEach(s => {
        const li = document.createElement("li");
        li.innerHTML = `<strong>✓ ${s}</strong>`;
        strengthContainer.appendChild(li);
      });
    } else {
      strengthContainer.innerHTML = `<li>Foundational skills developing well.</li>`;
    }

    // Target Weaknesses
    const weakContainer = document.getElementById("wow-weakness-list");
    weakContainer.innerHTML = "";
    if (data.weaknesses && data.weaknesses.length > 0) {
      data.weaknesses.forEach(w => {
        const li = document.createElement("li");
        li.innerHTML = `<strong>⚠ ${w}</strong>`;
        weakContainer.appendChild(li);
      });
    } else {
      weakContainer.innerHTML = `<li>No severe weak spots identified! Great job!</li>`;
    }

    // Strategy breakdown
    const strat = data.next_exam_strategy || {};
    const weakPct = strat.weak_focus_percent || 60;
    const newPct = strat.new_concepts_percent || 30;
    const revPct = strat.revision_percent || 10;

    const weakSegment = document.getElementById("meter-weak-seg");
    const newSegment = document.getElementById("meter-new-seg");
    const revSegment = document.getElementById("meter-rev-seg");

    if (weakSegment) weakSegment.style.width = `${weakPct}%`;
    if (newSegment) newSegment.style.width = `${newPct}%`;
    if (revSegment) revSegment.style.width = `${revPct}%`;

    document.getElementById("legend-weak-text").textContent = `${weakPct}% Weak Areas`;
    document.getElementById("legend-new-text").textContent = `${newPct}% New Concepts`;
    document.getElementById("legend-rev-text").textContent = `${revPct}% Revision`;

    if (strat.insights) {
      document.getElementById("strategy-insights-text").textContent = strat.insights;
    }

    // Download Markdown report button
    const downloadBtn = document.getElementById("download-report-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", () => {
        window.location.href = `${API_BASE}/exam/export/${user.id}/download`;
      });
    }

    // Print / Save PDF button
    const printBtn = document.getElementById("print-report-btn");
    if (printBtn) {
      printBtn.addEventListener("click", () => {
        window.print();
      });
    }

    // Practice again button
    const retryBtn = document.getElementById("practice-again-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        window.location.href = "/exam";
      });
    }

    // Switch topic button
    const homeBtn = document.getElementById("switch-topic-btn");
    if (homeBtn) {
      homeBtn.addEventListener("click", () => {
        window.location.href = "/";
      });
    }
  } catch (err) {
    console.error(err);
  }
}

// Route dispatcher
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  if (path === "/" || path.endsWith("index.html")) {
    initHomePage();
  } else if (path.startsWith("/exam") && !path.includes("history") && !path.includes("progress")) {
    initExamPage();
  } else if (path.startsWith("/dashboard") || path.endsWith("dashboard.html")) {
    initDashboardPage();
  } else if (path.startsWith("/result") || path.endsWith("result.html")) {
    initResultPage();
  }
});

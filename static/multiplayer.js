const socket = io();
const GAME_PIN = window.GAME_PIN;

socket.emit("join_room", { pin: GAME_PIN });

socket.on("spawn_word", data => {
  const colIndex = parseInt(data.column.replace("col", "")) - 1;
  spawnIntoColumn(data.word, colIndex);
});


socket.on("word_cleared", data => {
  clearColumnByIndex(data.column);
  updateScoreboard(data.scores);
});

socket.on("wave_update", data => {
  document.getElementById("wave").textContent = `Wave ${data.wave}`;
});

socket.on("game_over", data => {
  showLeaderboard(data.leaderboard);
});

function submitInput(value) {
  socket.emit("submit_word", {
    pin: GAME_PIN,
    word: value
  });
}

inputBox.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    submitInput(inputBox.value.trim());
    inputBox.value = "";
  }
});

function showLeaderboard(players) {
  const screen = document.getElementById("game");
  const results = document.getElementById("results");

  screen.style.display = "none";
  results.style.display = "block";

  const list = document.getElementById("leaderboard");
  list.innerHTML = "";

  players.forEach((p, i) => {
    const li = document.createElement("li");
    li.textContent = `${i + 1}. ${p.name} — ${p.score}`;
    list.appendChild(li);
  });
}


// GAME SCRIPT (wave-based, 1 word per column, 0.5s minimum spawn interval)
const columnElems = [
  document.getElementById("col1"),
  document.getElementById("col2"),
  document.getElementById("col3"),
  document.getElementById("col4")
];

// UI elements
const scoreDisplay = document.getElementById("score");
const livesDisplay = document.getElementById("lives");
const waveDisplay = document.getElementById("wave"); // optional: show "Wave X/10"
const inputBox = document.getElementById("input");

// Game state
let columnState = [null, null, null, null]; // null or { word, el, intervalId }
let spawnQueue = [];                         // words left to spawn this wave
let vocab = [];                              // full vocab list (passed in from template)
let currentWave = 0;
const totalWaves = 10;
let wordsPerWave = 0;
let wordsCompletedInWave = 0;
let score = 0;
let lives = 3;
let waveActive = false;

function delay(ms) { return new Promise(res => setTimeout(res, ms)); }

function updateHUD() {
  if (scoreDisplay) scoreDisplay.textContent = score;
  if (livesDisplay) livesDisplay.textContent = lives;
  if (waveDisplay) waveDisplay.textContent = `Wave ${Math.min(currentWave, totalWaves)}/${totalWaves}`;
}

function shuffleArray(arr) { return arr.slice().sort(() => Math.random() - 0.5); }

function endGame(msg) {

  const data = {
    player: window.playerID,
    score: score,
    deaths: 3 - lives,
    list_name: window.listName,
    token: window.token
  };
  console.log(data)
  fetch("/game/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  }).then(() => {
    window.location.href = "/";
  });

  // small timeout so DOM updates first
  setTimeout(() => alert(msg), 10);
  // clear all active intervals
  columnState.forEach(state => {
    if (state && state.intervalId) clearInterval(state.intervalId);
  });
}

// called from template: pass the words array
function startGame(wordsArray) {
  vocab = Array.isArray(wordsArray) ? wordsArray.slice() : [];
  wordsPerWave = vocab.length;
  currentWave = 0;
  score = 0;
  lives = 3;
  wordsCompletedInWave = 0;
  columnState = [null, null, null, null];
  spawnQueue = [];
  waveActive = false;
  updateHUD();
  // start first wave after a short delay
  setTimeout(() => startNextWave(), 800);
}

function startNextWave() {
  if (currentWave >= totalWaves) {
    endGame(`🎉 You finished all ${totalWaves} waves! Final Score: ${score}`);
    return;
  }
  currentWave++;
  wordsCompletedInWave = 0;
  waveActive = true;
  // prepare spawn queue: shuffled copy of vocab
  spawnQueue = shuffleArray(vocab);
  updateHUD();
  // spawn words for this wave (non-blocking)
  spawnWave();
}

/*
 spawnWave:
  - iterates through spawnQueue
  - for each word: waits until any column is empty, spawns into the first empty column,
    then waits 500ms (minimum spawn interval) before trying the next word.
*/

async function spawnWave() {
  while (spawnQueue.length > 0 && lives > 0) {
    // wait until at least one column is free
    await waitForEmptyColumnOrAbort();
    if (lives <= 0) return;

    // find first empty column index
    const colIndex = columnState.findIndex(s => s === null);
    if (colIndex === -1) {
      // no column free right now — short wait and loop again
      await delay(100);
      continue;
    }

    const word = spawnQueue.shift();
    spawnIntoColumn(word, colIndex);

    // enforce 0.5s minimum delay between spawns
    await delay(500);
  }

  // after we've queued all spawns, check for wave completion (it'll run when columns clear)
  checkWaveComplete();
}

function waitForEmptyColumnOrAbort() {
  return new Promise(resolve => {
    if (columnState.some(s => s === null) || spawnQueue.length === 0 || lives <= 0) {
      resolve();
      return;
    }
    const check = setInterval(() => {
      if (columnState.some(s => s === null) || spawnQueue.length === 0 || lives <= 0) {
        clearInterval(check);
        resolve();
      }
    }, 80);
  });
}

function spawnIntoColumn(word, colIndex) {
  // double-check the column element exists
  const container = columnElems[colIndex];
  if (!container) {
    console.error("Missing column element for index", colIndex);
    return;
  }

  // prevent duplicate spawn in same column
  if (columnState[colIndex]) {
    // column busy — push word back and rely on spawnWave's loop
    spawnQueue.unshift(word);
    return;
  }

  // create DOM element
const el = document.createElement("div");
el.className = "falling-word";
el.style.position = "absolute";
el.style.top = "0px";
el.style.left = "10px";
el.style.whiteSpace = "nowrap";
el.style.textAlign = "center";

// ❄️ Snowflake background
el.style.backgroundImage = "url('http://baipangwo.ddns.net/typing_cat3/images/9.svg')";
el.style.backgroundSize = "contain";
el.style.backgroundRepeat = "no-repeat";
el.style.backgroundPosition = "center";
el.style.width = "100px";   // adjust size as needed
el.style.height = "100px";
el.style.display = "flex";
el.style.flexDirection = "column";
el.style.alignItems = "center";
el.style.justifyContent = "center";

// 📝 Word
const span = document.createElement("span");
span.textContent = word;
span.style.position = "relative"; // keeps it above bg
span.style.zIndex = "2";

// 🧌 Gnome image
const gnome = document.createElement("img");
gnome.src = "http://baipangwo.ddns.net/typing_cat3/images/13.svg";
gnome.style.width = "70px";   // adjust size
gnome.style.height = "70px";
gnome.style.position = "absolute";
gnome.style.top = "-35px";    // place above the word
gnome.style.left = "50%";
gnome.style.transform = "translateX(-50%)";
gnome.style.zIndex = "3";
gnome.classList.add("gnome-dance");

el.appendChild(span);
el.appendChild(gnome);

container.appendChild(el);

  // start falling
  let top = 0;
  const fallSpeed = 2;     // pixels per tick
  const tickMs = 50;       // tick interval
  const intervalId = setInterval(() => {
    // if element was removed externally, stop
    if (!el.parentElement) {
      clearInterval(intervalId);
      columnState[colIndex] = null;
      return;
    }

    top += fallSpeed;
    el.style.top = top + "px";
    const elBottom = top + el.offsetHeight;
    const containerHeight = container.clientHeight;

    if (elBottom >= containerHeight - 2) {
      // word hit bottom -> missed
      clearInterval(intervalId);
      if (el.parentElement) el.remove();
      columnState[colIndex] = null;
      lives--;
      wordsCompletedInWave++;
      updateHUD();

      if (lives <= 0) {
        endGame(`💀 Game Over! Final Score: ${score}`);
        return;
      }
      // attempt to spawn more words for this wave if any left
      // spawnWave is running concurrently so it will pick up freed column
      checkWaveComplete();
    }
  }, tickMs);

  // record active word in column
  columnState[colIndex] = { word, el, intervalId };
}

// Called when player types a word
inputBox.addEventListener("keydown", function (e) {
  if (e.key !== "Enter") return;
  const value = inputBox.value.trim();
  if (!value) return;
  // find which column contains that exact word
  const colIndex = columnState.findIndex(s => s && s.word === value);
  if (colIndex !== -1) {
    // clear falling interval
    const state = columnState[colIndex];
    clearInterval(state.intervalId);
    if (state.el && state.el.parentElement) state.el.remove();
    columnState[colIndex] = null;

    score++;
    wordsCompletedInWave++;
    updateHUD();

    // spawnWave runs concurrently and will detect the freed column; check completion
    checkWaveComplete();
  }
  inputBox.value = "";
});

// checks whether the current wave is finished and triggers next wave or victory
function checkWaveComplete() {
  // wave complete only when we've spawned all words AND all columns are clear
  const allColumnsClear = columnState.every(s => s === null);
  const spawnQueueEmpty = spawnQueue.length === 0;

  if (spawnQueueEmpty && allColumnsClear) {
    waveActive = false;
    if (currentWave < totalWaves) {
      // small gap between waves
      setTimeout(() => startNextWave(), 900);
    } else {
      // finished last wave
      endGame(`🎉 You finished all ${totalWaves} waves! Final Score: ${score}`);
    }
  }
}

// hook-up helper: template will call startGame(words)
updateHUD();

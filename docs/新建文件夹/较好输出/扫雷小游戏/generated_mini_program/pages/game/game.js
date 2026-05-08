// pages/game/game.js
Page({
  data: {
    currentMode: 'dig',
    mineCount: 10,
    flagCount: 0,
    timeSeconds: 0,
    score: 0,
    revealedSafeCount: 0,
    gameState: 'ready',
    cellList: [],
    showResult: false,
    resultText: '',
    resultRevealed: 0,
    resultTime: 0,
    resultScore: 0
  },

  onLoad() {
    this.initGame();
  },

  initGame() {
    // 重置所有状态
    const cellList = [];
    for (let row = 0; row < 9; row++) {
      for (let col = 0; col < 9; col++) {
        cellList.push({
          row,
          col,
          isMine: false,
          adjacentMines: 0,
          isRevealed: false,
          isFlagged: false,
          isQuestioned: false,
          displayText: '',
          cellClass: 'cell cell-hidden'
        });
      }
    }
    this.setData({
      cellList,
      mineCount: 10,
      flagCount: 0,
      timeSeconds: 0,
      score: 0,
      revealedSafeCount: 0,
      gameState: 'ready',
      showResult: false,
      resultText: '',
      resultRevealed: 0,
      resultTime: 0,
      resultScore: 0
    });
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    this.firstClickDone = false;
  },

  // 布雷（首次点击后调用，保证点击位置不是雷）
  placeMines(safeRow, safeCol) {
    const cellList = this.data.cellList;
    const totalCells = 81;
    const mineCount = 10;
    let placed = 0;
    // 定义安全区域（点击格子及其周围）
    const safeSet = new Set();
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        const r = safeRow + dr;
        const c = safeCol + dc;
        if (r >= 0 && r < 9 && c >= 0 && c < 9) {
          safeSet.add(r * 9 + c);
        }
      }
    }
    // 随机布雷
    while (placed < mineCount) {
      const idx = Math.floor(Math.random() * totalCells);
      if (cellList[idx].isMine || safeSet.has(idx)) continue;
      cellList[idx].isMine = true;
      placed++;
    }
    // 计算adjacentMines
    for (let i = 0; i < totalCells; i++) {
      if (cellList[i].isMine) continue;
      let count = 0;
      const row = Math.floor(i / 9);
      const col = i % 9;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nr = row + dr;
          const nc = col + dc;
          if (nr >= 0 && nr < 9 && nc >= 0 && nc < 9) {
            if (cellList[nr * 9 + nc].isMine) count++;
          }
        }
      }
      cellList[i].adjacentMines = count;
    }
    // 更新数据，但先不渲染（后续会在点击时逐格更新）
    this.setData({ cellList });
  },

  // 切换模式
  switchMode() {
    if (this.data.gameState === 'won' || this.data.gameState === 'lost') return;
    const newMode = this.data.currentMode === 'dig' ? 'flag' : 'dig';
    this.setData({ currentMode: newMode });
  },

  // 点击格子事件
  onCellTap(e) {
    const index = e.currentTarget.dataset.index;
    const cell = this.data.cellList[index];
    if (cell.isRevealed) return;
    if (this.data.gameState === 'won' || this.data.gameState === 'lost') return;

    if (this.data.currentMode === 'dig') {
      // 如果标记了红旗或问号，不能点开
      if (cell.isFlagged || cell.isQuestioned) return;
      this.digCell(index);
    } else {
      // 插旗模式：循环无→红旗→问号→无
      this.flagCell(index);
    }
  },

  // 双击事件（点开模式有效）
  onCellDoubleTap(e) {
    if (this.data.currentMode !== 'dig') return;
    const index = e.currentTarget.dataset.index;
    const cell = this.data.cellList[index];
    if (!cell.isRevealed) return;
    if (cell.adjacentMines === 0) return;
    // 检查周围红旗数是否等于数字
    let flagCount = 0;
    const row = cell.row;
    const col = cell.col;
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (dr === 0 && dc === 0) continue;
        const nr = row + dr;
        const nc = col + dc;
        if (nr >= 0 && nr < 9 && nc >= 0 && nc < 9) {
          const idx = nr * 9 + nc;
          if (this.data.cellList[idx].isFlagged) flagCount++;
        }
      }
    }
    if (flagCount === cell.adjacentMines) {
      // 翻开周围未标记的格子
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nr = row + dr;
          const nc = col + dc;
          if (nr >= 0 && nr < 9 && nc >= 0 && nc < 9) {
            const idx = nr * 9 + nc;
            const neighbor = this.data.cellList[idx];
            if (!neighbor.isRevealed && !neighbor.isFlagged && !neighbor.isQuestioned) {
              this.digCell(idx);
            }
          }
        }
      }
    }
  },

  digCell(index) {
    const cell = this.data.cellList[index];
    if (cell.isRevealed) return;
    // 首次点击保护
    if (!this.firstClickDone) {
      this.firstClickDone = true;
      this.placeMines(cell.row, cell.col);
      // 启动计时器
      this.startTimer();
      // 设置游戏状态为playing
      this.setData({ gameState: 'playing' });
      // 重新获取当前cell（因为布雷可能改变了数据）
      const updatedCell = this.data.cellList[index];
      if (updatedCell.isMine) {
        // 如果首次点击恰巧变成了雷（理论上不会，因为placeMines保证了安全区域）
        // 但以防万一，重新布雷
        this.placeMines(cell.row, cell.col);
      }
    }
    // 递归翻开（BFS）
    this.revealCell(index);
  },

  revealCell(index) {
    const cellList = this.data.cellList;
    const cell = cellList[index];
    if (cell.isRevealed || cell.isFlagged || cell.isQuestioned) return;

    // 标记翻开
    cell.isRevealed = true;
    cell.isFlagged = false;
    cell.isQuestioned = false;
    // 更新显示
    if (cell.isMine) {
      cell.displayText = '💣';
      cell.cellClass = 'cell cell-revealed cell-mine';
      this.setData({
        [`cellList[${index}]`]: cell
      });
      // 游戏结束：踩雷
      this.gameOver(false);
      return;
    }
    // 非雷
    this.data.revealedSafeCount++;
    if (cell.adjacentMines > 0) {
      cell.displayText = cell.adjacentMines.toString();
      const colors = ['', '#0000FF', '#008000', '#FF0000', '#000080', '#800000', '#008080', '#000000', '#808080'];
      cell.cellClass = `cell cell-revealed cell-number color-${cell.adjacentMines}`;
      // 使用data-path更新单个格子的样式和文本
      this.setData({
        [`cellList[${index}]`]: cell
      });
    } else {
      cell.displayText = '';
      cell.cellClass = 'cell cell-revealed cell-empty';
      this.setData({
        [`cellList[${index}]`]: cell
      });
      // 连锁翻开周围
      const row = cell.row;
      const col = cell.col;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nr = row + dr;
          const nc = col + dc;
          if (nr >= 0 && nr < 9 && nc >= 0 && nc < 9) {
            const idx = nr * 9 + nc;
            const neighbor = this.data.cellList[idx];
            if (!neighbor.isRevealed && !neighbor.isFlagged && !neighbor.isQuestioned) {
              this.revealCell(idx);
            }
          }
        }
      }
    }
    // 检查胜利
    if (this.data.revealedSafeCount === 71) {
      this.gameOver(true);
    }
  },

  flagCell(index) {
    const cell = this.data.cellList[index];
    if (cell.isRevealed) return;
    let newFlagged = false;
    let newQuestioned = false;
    if (!cell.isFlagged && !cell.isQuestioned) {
      // 无标记 → 红旗
      newFlagged = true;
      newQuestioned = false;
    } else if (cell.isFlagged) {
      // 红旗 → 问号
      newFlagged = false;
      newQuestioned = true;
    } else if (cell.isQuestioned) {
      // 问号 → 无标记
      newFlagged = false;
      newQuestioned = false;
    }
    cell.isFlagged = newFlagged;
    cell.isQuestioned = newQuestioned;
    // 更新显示文本和类
    if (cell.isFlagged) {
      cell.displayText = '🚩';
      cell.cellClass = 'cell cell-hidden cell-flagged';
      this.data.flagCount++;
    } else if (cell.isQuestioned) {
      cell.displayText = '?';
      cell.cellClass = 'cell cell-hidden cell-questioned';
      this.data.flagCount--;
    } else {
      cell.displayText = '';
      cell.cellClass = 'cell cell-hidden';
      // 如果之前是flag或question，需要减少flagCount? 在循环中处理了，但要注意从question变为无时flagCount不变
      // 实际上循环中只有从红旗变为问号时flagCount减1；从问号变为无时flagCount不变
      // 所以我们得在具体变化时调整
      // 上面的逻辑中，从红旗变为问号时已经减了，但从问号变为无时没有减，但flagCount在变为问号时已经减过一次了，所以不需要再减
      // 但为了准确，我们直接根据新状态设置flagCount
    }
    // 重新计算旗子数
    // 更好的方式是重新遍历计算flagCount，但为了性能，我们手动调整
    // 我们手动维护flagCount：从无到旗+1，旗到问号-1，问号到无不变（因为旗已经减过了）
    // 所以更简单：重新计算flagCount
    let flagCount = 0;
    const cellList = this.data.cellList;
    for (let i = 0; i < cellList.length; i++) {
      if (cellList[i].isFlagged) flagCount++;
    }
    this.setData({
      [`cellList[${index}]`]: cell,
      flagCount: flagCount
    });
  },

  gameOver(isWin) {
    // 停止计时
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    const state = isWin ? 'won' : 'lost';
    // 如果是失败，翻开所有地雷以及标记错误
    if (!isWin) {
      const cellList = this.data.cellList;
      for (let i = 0; i < cellList.length; i++) {
        const cell = cellList[i];
        if (cell.isMine && !cell.isRevealed) {
          cell.isRevealed = true;
          cell.displayText = '💣';
          cell.cellClass = 'cell cell-revealed cell-mine';
          this.setData({
            [`cellList[${i}]`]: cell
          });
        }
        // 如果插旗位置不是雷，显示叉
        if (cell.isFlagged && !cell.isMine) {
          cell.isFlagged = false;
          cell.isQuestioned = false;
          cell.isRevealed = true;
          cell.displayText = '❌';
          cell.cellClass = 'cell cell-revealed cell-wrong';
          this.setData({
            [`cellList[${i}]`]: cell
          });
        }
      }
    }
    // 计算分数
    const revealed = this.data.revealedSafeCount;
    const time = this.data.timeSeconds;
    const score = Math.floor(revealed * 100 / (1 + time));
    const resultText = isWin ? '恭喜你赢了！' : '很遗憾，踩到地雷了！';
    this.setData({
      gameState: state,
      score: score,
      showResult: true,
      resultText: resultText,
      resultRevealed: revealed,
      resultTime: time,
      resultScore: score
    });
  },

  startTimer() {
    this.timerId = setInterval(() => {
      this.setData({
        timeSeconds: this.data.timeSeconds + 1
      });
    }, 1000);
  },

  // 重新开始
  restartGame() {
    this.initGame();
  },

  // 点击遮罩关闭弹窗（重置）
  onResultTap() {
    this.restartGame();
  },

  onUnload() {
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }
});
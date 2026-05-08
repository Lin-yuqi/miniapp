App({
  globalData: {
    userInfo: null,
    isLoggedIn: false
  },

  onLaunch() {
    const userInfo = wx.getStorageSync('userInfo') || null;
    this.globalData.userInfo = userInfo;
    this.globalData.isLoggedIn = !!userInfo;
  },

  setUserInfo(userInfo) {
    this.globalData.userInfo = userInfo;
    this.globalData.isLoggedIn = !!userInfo;
    wx.setStorageSync('userInfo', userInfo);
  },

  clearUserInfo() {
    this.globalData.userInfo = null;
    this.globalData.isLoggedIn = false;
    wx.removeStorageSync('userInfo');
  }
});

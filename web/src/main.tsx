import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import App from "./App";
import "./index.css";

dayjs.locale("zh-cn");

// 视觉参考 Answerbit：靛紫主色、浅色侧栏、白色大圆角卡片
const theme = {
  token: { colorPrimary: "#5B5CF6", borderRadius: 8, colorBgLayout: "#F5F6FA", fontSize: 14 },
  components: {
    Layout: { siderBg: "#FFFFFF", headerBg: "#FFFFFF", bodyBg: "#F5F6FA" },
    Menu: { itemSelectedBg: "#EEF0FF", itemSelectedColor: "#5B5CF6", groupTitleColor: "#9AA0AC", itemHeight: 38 },
    Card: { borderRadiusLG: 14 },
  },
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={theme}>
      <App />
    </ConfigProvider>
  </StrictMode>,
);

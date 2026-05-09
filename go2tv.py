import upnpclient
import logging

# 配置简单的日志输出
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DLNACaster:
    def __init__(self, timeout=5):
        self.timeout = timeout
        self.devices = []

    def discover_devices(self):
        """扫描局域网内的 DLNA 设备"""
        try:
            logger.info("正在扫描局域网设备...")
            self.devices = upnpclient.discover(timeout=self.timeout)
            return [d.friendly_name for d in self.devices]
        except Exception as e:
            logger.error(f"扫描设备失败: {e}")
            return []

    def find_device(self, friendly_name):
        """根据名称匹配设备"""
        if not self.devices:
            self.discover_devices()

        for d in self.devices:
            if friendly_name in d.friendly_name:
                return d
        return None

    def cast(self, video_url, device_name="小米盒子"):
        """
        核心投屏方法
        :param video_url: 影片地址
        :param device_name: 设备名称关键字
        :return: (bool, message)
        """
        try:
            # 1. 查找设备
            tv = self.find_device(device_name)
            if not tv:
                return False, f"未找到设备: {device_name}"

            # 2. 设置 URI
            # 部分设备需要特定的 InstanceID，默认为 0
            tv.AVTransport.SetAVTransportURI(
                InstanceID=0, CurrentURI=video_url, CurrentURIMetaData=""
            )

            # 3. 发送播放指令
            tv.AVTransport.Play(InstanceID=0, Speed="1")

            logger.info(f"已成功向 {tv.friendly_name} 推送地址: {video_url}")
            return True, "投屏成功"

        except Exception as e:
            logger.error(f"投屏过程中出错: {e}")
            return False, str(e)


# --- 快速测试代码 ---
if __name__ == "__main__":
    caster = DLNACaster()
    # 打印发现的所有设备
    print("发现的设备:", caster.discover_devices())

    # # 执行投屏 target_url=视频文件的局域网http下载地址
    # target_url = "http://192.168.2.22:8000/1.mp4"
    # success, msg = caster.cast(target_url, "小米盒子111111")
    # print(f"结果: {msg}")

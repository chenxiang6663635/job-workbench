# 下载

**最新版本：{{VERSION}}**（{{RELEASE_DATE}} 发布）

English: [Download](download.en.md)

## 主通道：GitHub Releases

[下载 Windows 安装包](https://github.com/chenxiang6663635/job-workbench/releases/latest){ .md-button .md-button--primary }

打开发布页后，在 **Assets** 区下载 `job-workbench-setup-{{VERSION}}-win64.exe`——Windows x64 安装包，向导式安装，免 Python / Node 环境。

> 国内网络访问 GitHub 可能不畅。如果发布页打不开、或下载中途断流，请走下面的备用通道。

## 备用通道（国内网络）

在 [Issues](https://github.com/chenxiang6663635/job-workbench/issues) 留言（写清需要的版本号），或通过[仓库主页](https://github.com/chenxiang6663635/job-workbench)联系作者——我们会回复一个当时的备用下载链接。

如实说明：备用链接由人工上传与维护，可能滞后于正式 Releases；能直连 GitHub 时请优先使用主通道。

## 未签名说明（SmartScreen）

安装包尚未做代码签名。首次运行时 Windows 可能显示「Windows 已保护你的电脑」——这是未签名软件的正常提示：点「**更多信息**」→「**仍要运行**」。

SmartScreen 信誉按版本重新积累，**后续版本升级后可能再次提示**；签名的缺位不影响自动更新（完整性以 `latest.yml` 里的哈希为准）。

## 校验下载完整性

**自 v26.9.0 起**，每个 Release 附 `SHA256SUMS.txt`（安装包与 `latest.yml` 的 SHA256 哈希）。下载完成后，在 PowerShell 或 CMD 里执行（文件名换成你实际下载的那个）：

```bat
certutil -hashfile job-workbench-setup-{{VERSION}}-win64.exe SHA256
```

把输出与 Release 页 `SHA256SUMS.txt` 中同名文件的哈希对照：一致说明文件完好、与发布者上传的一致。如实说明：这证明的是**完整性**；未签名场景下，它不构成发布者身份认证。

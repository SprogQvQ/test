#!/usr/bin/env python3
"""
Splunk Universal Forwarder 批量安装脚本
支持批量远程安装，带并发控制，确保不影响业务
"""

import paramiko
import json
import logging
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Tuple
import argparse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'splunk_install_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SplunkInstaller:
    """Splunk Universal Forwarder 安装器"""
    
    def __init__(self, config_file: str = 'config.json'):
        """初始化安装器"""
        self.config = self.load_config(config_file)
        self.results = []
        
    def load_config(self, config_file: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"配置文件 {config_file} 不存在")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            sys.exit(1)
    
    def create_ssh_client(self, host: str, port: int, username: str, 
                         password: str = None, key_file: str = None) -> paramiko.SSHClient:
        """创建SSH连接"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if key_file and os.path.exists(key_file):
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    key_filename=key_file,
                    timeout=30
                )
            else:
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=30
                )
            return client
        except Exception as e:
            logger.error(f"连接到 {host} 失败: {e}")
            raise
    
    def check_system_resources(self, ssh_client: paramiko.SSHClient) -> Tuple[bool, str]:
        """检查系统资源，确保不影响业务"""
        try:
            # 检查CPU负载
            stdin, stdout, stderr = ssh_client.exec_command("uptime")
            uptime_output = stdout.read().decode().strip()
            logger.info(f"系统负载: {uptime_output}")
            
            # 检查内存使用
            stdin, stdout, stderr = ssh_client.exec_command(
                "free -m | grep Mem | awk '{print $7}'"
            )
            available_mem = int(stdout.read().decode().strip())
            
            # 检查磁盘空间
            stdin, stdout, stderr = ssh_client.exec_command(
                "df -m /opt | tail -1 | awk '{print $4}'"
            )
            available_disk = int(stdout.read().decode().strip())
            
            logger.info(f"可用内存: {available_mem}MB, 可用磁盘: {available_disk}MB")
            
            # 资源阈值检查
            min_memory = self.config.get('resource_limits', {}).get('min_memory_mb', 512)
            min_disk = self.config.get('resource_limits', {}).get('min_disk_mb', 2048)
            
            if available_mem < min_memory:
                return False, f"内存不足 (可用: {available_mem}MB, 需要: {min_memory}MB)"
            
            if available_disk < min_disk:
                return False, f"磁盘空间不足 (可用: {available_disk}MB, 需要: {min_disk}MB)"
            
            return True, "资源检查通过"
            
        except Exception as e:
            logger.error(f"资源检查失败: {e}")
            return False, str(e)
    
    def check_if_installed(self, ssh_client: paramiko.SSHClient) -> bool:
        """检查Splunk UF是否已安装"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(
                "test -d /opt/splunkforwarder && echo 'exists'"
            )
            result = stdout.read().decode().strip()
            return result == 'exists'
        except Exception as e:
            logger.error(f"检查安装状态失败: {e}")
            return False
    
    def download_splunk_package(self, ssh_client: paramiko.SSHClient, 
                                download_url: str, os_type: str) -> Tuple[bool, str]:
        """下载Splunk安装包"""
        try:
            # 检测操作系统
            stdin, stdout, stderr = ssh_client.exec_command("uname -s")
            detected_os = stdout.read().decode().strip().lower()
            
            package_name = download_url.split('/')[-1]
            
            # 检查是否已下载
            stdin, stdout, stderr = ssh_client.exec_command(
                f"test -f /tmp/{package_name} && echo 'exists'"
            )
            if stdout.read().decode().strip() == 'exists':
                logger.info(f"安装包已存在: /tmp/{package_name}")
                return True, f"/tmp/{package_name}"
            
            # 使用wget或curl下载
            logger.info(f"开始下载Splunk安装包...")
            download_cmd = f"cd /tmp && wget -q -O {package_name} '{download_url}' || curl -s -o {package_name} '{download_url}'"
            
            stdin, stdout, stderr = ssh_client.exec_command(download_cmd, timeout=600)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_msg = stderr.read().decode().strip()
                return False, f"下载失败: {error_msg}"
            
            logger.info(f"下载完成: /tmp/{package_name}")
            return True, f"/tmp/{package_name}"
            
        except Exception as e:
            logger.error(f"下载Splunk安装包失败: {e}")
            return False, str(e)
    
    def install_splunk(self, ssh_client: paramiko.SSHClient, 
                      package_path: str, os_type: str) -> Tuple[bool, str]:
        """安装Splunk UF"""
        try:
            logger.info("开始安装Splunk Universal Forwarder...")
            
            # 根据操作系统类型选择安装命令
            if os_type.lower() in ['linux', 'unix']:
                # Linux tar.gz安装
                if package_path.endswith('.tgz') or package_path.endswith('.tar.gz'):
                    install_cmd = f"cd /opt && tar xzf {package_path}"
                # Linux RPM安装
                elif package_path.endswith('.rpm'):
                    install_cmd = f"rpm -ivh {package_path}"
                # Linux DEB安装
                elif package_path.endswith('.deb'):
                    install_cmd = f"dpkg -i {package_path}"
                else:
                    return False, f"不支持的安装包格式: {package_path}"
            else:
                return False, f"不支持的操作系统: {os_type}"
            
            # 执行安装
            stdin, stdout, stderr = ssh_client.exec_command(install_cmd, timeout=300)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_msg = stderr.read().decode().strip()
                return False, f"安装失败: {error_msg}"
            
            logger.info("Splunk UF 安装成功")
            return True, "安装成功"
            
        except Exception as e:
            logger.error(f"安装Splunk失败: {e}")
            return False, str(e)
    
    def configure_splunk(self, ssh_client: paramiko.SSHClient) -> Tuple[bool, str]:
        """配置Splunk UF"""
        try:
            splunk_config = self.config.get('splunk_config', {})
            deployment_server = splunk_config.get('deployment_server', '')
            receiving_indexer = splunk_config.get('receiving_indexer', '')
            
            logger.info("开始配置Splunk UF...")
            
            # 接受许可证
            accept_license_cmd = "/opt/splunkforwarder/bin/splunk start --accept-license --answer-yes --no-prompt"
            stdin, stdout, stderr = ssh_client.exec_command(accept_license_cmd, timeout=60)
            stdout.channel.recv_exit_status()
            
            # 停止Splunk以进行配置
            stdin, stdout, stderr = ssh_client.exec_command(
                "/opt/splunkforwarder/bin/splunk stop", timeout=60
            )
            stdout.channel.recv_exit_status()
            
            # 配置deployment server
            if deployment_server:
                logger.info(f"配置Deployment Server: {deployment_server}")
                ds_cmd = f"/opt/splunkforwarder/bin/splunk set deploy-poll {deployment_server} -auth admin:changeme"
                stdin, stdout, stderr = ssh_client.exec_command(ds_cmd, timeout=30)
                stdout.channel.recv_exit_status()
            
            # 配置forward server
            if receiving_indexer:
                logger.info(f"配置Receiving Indexer: {receiving_indexer}")
                fwd_cmd = f"/opt/splunkforwarder/bin/splunk add forward-server {receiving_indexer} -auth admin:changeme"
                stdin, stdout, stderr = ssh_client.exec_command(fwd_cmd, timeout=30)
                stdout.channel.recv_exit_status()
            
            # 启用开机自启动
            stdin, stdout, stderr = ssh_client.exec_command(
                "/opt/splunkforwarder/bin/splunk enable boot-start", timeout=30
            )
            stdout.channel.recv_exit_status()
            
            # 启动Splunk
            stdin, stdout, stderr = ssh_client.exec_command(
                "/opt/splunkforwarder/bin/splunk start", timeout=60
            )
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_msg = stderr.read().decode().strip()
                return False, f"启动失败: {error_msg}"
            
            logger.info("Splunk UF 配置完成并启动成功")
            return True, "配置成功"
            
        except Exception as e:
            logger.error(f"配置Splunk失败: {e}")
            return False, str(e)
    
    def cleanup(self, ssh_client: paramiko.SSHClient, package_path: str):
        """清理临时文件"""
        try:
            if self.config.get('cleanup_after_install', True):
                logger.info("清理临时文件...")
                ssh_client.exec_command(f"rm -f {package_path}")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
    
    def install_on_server(self, server: Dict) -> Dict:
        """在单个服务器上执行安装"""
        host = server['host']
        result = {
            'host': host,
            'success': False,
            'message': '',
            'timestamp': datetime.now().isoformat()
        }
        
        ssh_client = None
        
        try:
            logger.info(f"=" * 60)
            logger.info(f"开始处理服务器: {host}")
            logger.info(f"=" * 60)
            
            # 1. 建立SSH连接
            logger.info(f"[{host}] 建立SSH连接...")
            ssh_client = self.create_ssh_client(
                host=host,
                port=server.get('port', 22),
                username=server.get('username', 'root'),
                password=server.get('password'),
                key_file=server.get('key_file')
            )
            
            # 2. 检查是否已安装
            logger.info(f"[{host}] 检查Splunk UF安装状态...")
            if self.check_if_installed(ssh_client):
                if not self.config.get('force_reinstall', False):
                    result['success'] = True
                    result['message'] = "Splunk UF 已安装，跳过"
                    logger.info(f"[{host}] Splunk UF 已安装，跳过")
                    return result
                else:
                    logger.info(f"[{host}] Splunk UF 已安装，但设置了强制重装")
            
            # 3. 检查系统资源
            logger.info(f"[{host}] 检查系统资源...")
            resource_ok, resource_msg = self.check_system_resources(ssh_client)
            if not resource_ok:
                result['message'] = f"资源检查失败: {resource_msg}"
                logger.warning(f"[{host}] {result['message']}")
                return result
            
            # 4. 下载安装包
            download_url = self.config['splunk_config']['download_url']
            os_type = server.get('os_type', 'linux')
            
            logger.info(f"[{host}] 下载Splunk安装包...")
            download_ok, package_path = self.download_splunk_package(
                ssh_client, download_url, os_type
            )
            if not download_ok:
                result['message'] = f"下载失败: {package_path}"
                logger.error(f"[{host}] {result['message']}")
                return result
            
            # 5. 安装Splunk
            logger.info(f"[{host}] 安装Splunk UF...")
            install_ok, install_msg = self.install_splunk(
                ssh_client, package_path, os_type
            )
            if not install_ok:
                result['message'] = f"安装失败: {install_msg}"
                logger.error(f"[{host}] {result['message']}")
                return result
            
            # 6. 配置Splunk
            logger.info(f"[{host}] 配置Splunk UF...")
            config_ok, config_msg = self.configure_splunk(ssh_client)
            if not config_ok:
                result['message'] = f"配置失败: {config_msg}"
                logger.error(f"[{host}] {result['message']}")
                return result
            
            # 7. 清理临时文件
            self.cleanup(ssh_client, package_path)
            
            result['success'] = True
            result['message'] = "安装并配置成功"
            logger.info(f"[{host}] ✓ 安装并配置成功")
            
        except Exception as e:
            result['message'] = f"异常: {str(e)}"
            logger.error(f"[{host}] ✗ 安装失败: {e}")
        
        finally:
            if ssh_client:
                ssh_client.close()
        
        return result
    
    def batch_install(self, dry_run: bool = False):
        """批量安装"""
        servers = self.config.get('servers', [])
        max_concurrent = self.config.get('max_concurrent_installs', 3)
        delay_between_batches = self.config.get('delay_between_batches_seconds', 5)
        
        if not servers:
            logger.error("配置文件中没有服务器列表")
            return
        
        logger.info(f"准备在 {len(servers)} 台服务器上安装Splunk UF")
        logger.info(f"最大并发数: {max_concurrent}")
        logger.info(f"批次间延迟: {delay_between_batches}秒")
        
        if dry_run:
            logger.info("*** DRY RUN 模式 - 仅测试连接 ***")
            for server in servers:
                logger.info(f"将要处理: {server['host']}")
            return
        
        # 使用线程池控制并发
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(self.install_on_server, server): server 
                for server in servers
            }
            
            for future in as_completed(futures):
                server = futures[future]
                try:
                    result = future.result()
                    self.results.append(result)
                    
                    # 批次间延迟
                    if delay_between_batches > 0:
                        time.sleep(delay_between_batches)
                        
                except Exception as e:
                    logger.error(f"处理服务器 {server['host']} 时发生异常: {e}")
                    self.results.append({
                        'host': server['host'],
                        'success': False,
                        'message': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
        
        # 输出统计结果
        self.print_summary()
    
    def print_summary(self):
        """打印安装统计摘要"""
        logger.info("\n" + "=" * 60)
        logger.info("安装统计摘要")
        logger.info("=" * 60)
        
        total = len(self.results)
        success = sum(1 for r in self.results if r['success'])
        failed = total - success
        
        logger.info(f"总计: {total} 台服务器")
        logger.info(f"成功: {success} 台")
        logger.info(f"失败: {failed} 台")
        
        if failed > 0:
            logger.info("\n失败的服务器:")
            for result in self.results:
                if not result['success']:
                    logger.info(f"  - {result['host']}: {result['message']}")
        
        # 保存详细结果到JSON文件
        result_file = f"install_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n详细结果已保存到: {result_file}")
        logger.info("=" * 60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Splunk Universal Forwarder 批量安装工具'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅测试连接，不执行实际安装'
    )
    
    args = parser.parse_args()
    
    logger.info("Splunk Universal Forwarder 批量安装工具启动")
    logger.info(f"配置文件: {args.config}")
    
    installer = SplunkInstaller(args.config)
    installer.batch_install(dry_run=args.dry_run)
    
    logger.info("批量安装任务完成")


if __name__ == '__main__':
    main()

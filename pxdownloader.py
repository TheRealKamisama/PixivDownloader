from bs4 import BeautifulSoup
import os
import requests
import time
import threading
import queue
import sys

def mk_dir(dir_name):
    dir_name = str(dir_name)
    dir_path = os.path.join(sys.path[0], dir_name)
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    return dir_path

class Getter:
    def __init__(self, id, _mode, images_count, word):
        self.id = id
        self.mode = _mode
        self.images_count = images_count
        self.word = word

    def favorite_getter(self):
        header = {
                'Referer': 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36',
                'Cookie': open('cookies.txt').read()
        }
        proxies = { 
                "http": "http://"+"127.0.0.1:1080",
                "https": "http://"+"127.0.0.1:1080",
        }
        i = 1
        result = []
        while True:
                try:
                    html = requests.get('https://www.pixiv.net/bookmark.php?id=%s&rest=show&p=%s' % (str(self.id), i), headers=header, proxies=proxies).content
                except Exception:
                    print('触发反爬，睡觉五秒')
                    time.sleep(5)
                    continue
                i += 1
                print('正在获取用户第%s页收藏(每页20张图)' % (str(i)))
                soup = BeautifulSoup(html, "html.parser")
                works = soup.find_all('a', class_ = 'work')
                if len(works) == 0:
                    print(str(len(result)))
                    return result
                for obj in works:
                    one_id = obj.get('href')[len('member_illust.php?mode=medium&illust_id='):]
                    result.append(one_id)
                    if len(result) >= self.images_count:
                        print(str(len(result)))
                        return result

    def illust_getter(self, ids):
        # 娘炮才需要可维护性，猛男都是删了重构
        result = []
        page = 1
        if self.mode == 1:
            _echo = '画师作品'
            _type = 'member_illust'
        elif self.mode == 2:
            _echo = '用户收藏'
            _type = None
        elif self.mode == 3:
            _echo = '搜索页面'
            _type = 'search'
        elif self.mode == 4:
            _echo = '作品获取'
            _type = 'illust'
        while True:
            if self.mode != 4 and self.mode != 2:
                print('[illust_getter]:正在获取%s，第%s页(每页1000张图)：' % (_echo, page))
                try:
                    one_step_result = requests.get(
                        url='https://api.imjad.cn/pixiv/v1/?type=%s&id=%s&per_page=1000&page=%s&word=%s' % (_type, self.id, page, self.word)).json()
                except Exception as e:
                    print('Error:%s' % e, '正在重试，请检查您的网络连接')
                    continue
                if one_step_result is False:
                    continue
                if one_step_result['status'] == 'failure':
                    break
                print('[illust_getter]:成功获取%s第%s页(每页1000张图)：' % (_echo, page))
                result += one_step_result['response']
                page += 1
                if one_step_result['pagination']['next'] is None:
                    break                    
            else:
                image_index = 1
                for id in ids:
                    print('[illust_getter]:正在获取第%s张图片的详细信息.' % (image_index))
                    try:
                        one_step_result = requests.get(
                            url='https://api.imjad.cn/pixiv/v1/?type=illust&id=%s' % (id)).json()
                    except Exception as e:
                        print('Error:%s' % e, '正在重试，请检查您的网络连接')
                        continue
                    print("[illust_getter]:已经获取一张图片")
                    try:
                        result += one_step_result['response']
                    except KeyError as e:
                        continue
                    image_index += 1
                    
                break
        return result


class CheckerThreading(threading.Thread):

    def __init__(self, q1, q2, threading_id):
        threading.Thread.__init__(self)
        self.q1 = q1
        self.q2 = q2
        self.id = threading_id

    def illust_detail(self, illust_id):
        while True:
            try:
                new_illust = requests.get(url='https://api.imjad.cn/pixiv/v1/?type=illust&id=%s' % str(illust_id)).json()['response'][0]
                break
            except Exception as e:
                print('illust_detail error %s : ' % e, illust_id)
                return False
        return new_illust

    def run(self):
        while True:
            if not self.q1.empty():
                got_queue_content = self.q1.get()
                got_new_illust = self.illust_detail(got_queue_content[1])
                if got_new_illust is not False:
                    got_metadata = got_new_illust['metadata']
                    self.q2.put([got_queue_content[0], got_metadata])

                time.sleep(0.1)
            else:
                break


# 此处的轮子来自于@xyqyear
class Checker:

    def __init__(self, _illusts, threading_num, images_count):
        self.illusts = _illusts
        self.queue = queue.Queue()
        self.meta_queue = queue.Queue()
        self.threading_num = threading_num
        self.images_count = images_count

    def check(self):
        num = 0
        illusts_len = min(self.images_count, len(self.illusts))# forkyou
        for ill_index in range(0, illusts_len):
            # 如果page——count大于1而且metadata为None的话,就更新
            if self.illusts[ill_index]['page_count'] > 1 and self.illusts[ill_index]['metadata'] is None:
                # 加入队列，格式为  [图片在illusts中所在的位置，作品id]
                self.queue.put([ill_index,self.illusts[ill_index]['id']])
                num += 1
        threading_list = []
        # 创建线程并开始线程
        for t in range(1, self.threading_num + 1):
            new_threading = CheckerThreading(self.queue, self.meta_queue, t)
            threading_list.append(new_threading)
            new_threading.start()
        # 等待线程完成
        for t in threading_list:
            t.join()
        # 更新metadata数据
        while True:
            if not self.meta_queue.empty():
                got_queue_content = self.meta_queue.get()
                got_metadata = got_queue_content[1]
                self.illusts[got_queue_content[0]]['metadata'] = got_metadata
            else:
                break
        return [self.illusts, num]
class DownloadThreading(threading.Thread):

    def __init__(self, que, tid, _folder):
        threading.Thread.__init__(self)
        self.queue = que
        self.tid = tid
        self.folder = _folder
        # 请求头不加Referer不给下载=w=，会403拒绝访问
        self.headers = {
            'Referer': 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id',
            'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
        }

    def run(self):
        # 如果队列不为空，则下载，否则退出线程
        while True:
            if not self.queue.empty():
                # 获取队列中下一张图片
                img_url = self.queue.get()
                index = img_url.rindex('/')
                # 截取/以后的内容即为图片文件名
                img_name = img_url[index+1:]
                # 获取图片
                while True:
                    # 如果抓取到错误则重试
                    try:
                        path = os.path.join(sys.path[0],self.folder)
                        print('[Threading %s]: 正在下载图片 %s ,剩余 %s 张图未下载' % (self.tid, img_name, self.queue.qsize()))
                        file_path = os.path.join(path, img_name)
                        if os.path.exists(file_path):
                            print('[Threading %s]: 图片 %s 已下载' % (self.tid, img_name))
                            break
                        img = requests.get(img_url, headers=self.headers, timeout = 60).content
                        # 写入图片内容到文件
                        with open(file_path, 'wb') as f:  # 图片要用b
                            f.write(img)
                        break
                    except Exception as e:
                        print('Error:',e)
                        continue
            else:
                break
# 此处的轮子来自于@xyqyear
class Downloader:

    def __init__(self, urls_list, threading_num, _folder):
        # 实例化一个新队列
        self.queue = queue.Queue()
        self.threading_num = threading_num
        self.folder = str(_folder)
        # 添加url到队列 queue.put(something)为添加something到队列
        for _url in urls_list:
            self.queue.put(_url)

    def work(self):
        threading_list = []
        # 创建线程并开始线程
        for t in range(1,self.threading_num+1):
            print('创建线程:',t)
            new_threading = DownloadThreading(self.queue, t, self.folder)
            threading_list.append(new_threading)
            new_threading.start()
        # 等待线程完成
        for t in threading_list:
            t.join()
def getInt(message):
    strint = input(message)
    try:
        num = int(strint)
        return num
    except ValueError:
        return None
while True:
    mode = getInt("要下载此用户的作品请输入1，要下载收藏夹请输入2，要下载搜索请输入3：")
    if mode is None:
        continue
    else:
        break
if mode == 3:
    searcher_word = input("请输入要搜索的tag：")
    user_id = None
else:
    searcher_word = None
    while True:
        user_id = getInt("请输入要下载的用户的id：")
        if user_id is None:
            continue
        else:
            break
while True:
    images_count = getInt('是否使用计数下载，是则请输入数量，否则请输入除数字外字符或直接回车：')
    if images_count is None:
        images_count = 200000000
        break
    else:
        break
folder_name = input("请输入文件夹名称，不输入将会使用（id/tag+模式）:")
if mode == 1:
    echo = '画师作品'
elif mode == 2:
    echo = '用户收藏'
elif mode == 3:
    echo = '搜索页面'

print('正在获取', echo)
getter = Getter(user_id, mode, images_count ,searcher_word)
ids = None
if mode == 2:
    ids = getter.favorite_getter()
    illusts = getter.illust_getter(ids)
else:
    illusts = getter.illust_getter(ids)
print(len(illusts))
print(echo, '获取完毕')
print('正在校验')
if mode != 2:
    checker = Checker(illusts, 1 ,images_count)
    check_result = checker.check()
    illusts = check_result[0]
print('校验完毕')
print('正在获取图片的url')
illust_index = 0
urls = []
for illust in illusts: 
    if illust['page_count'] == 1:
        urls.append(illust['image_urls']['large'])
        continue
    if illust['metadata'] is None:
        urls.append(illust['image_urls']['large'])
    else:
        pages = illust['metadata']['pages']
        for url in pages:
            urls.append(url['image_urls']['large'])
    illust_index += 1
    if illust_index == images_count:
        break
print('获取图片urls完成')
print('url数量:' + str(len(urls)))
print('************开始下载!!!!************')
if folder_name == "":
    if mode != 3:
        folder_name = str(user_id) + '_' + echo
    else:
        folder_name = str(searcher_word) + '_' + echo
mk_dir(folder_name)
downloader = Downloader(urls, 16, folder_name)
downloader.work()
print('下载完毕！程序结束.')
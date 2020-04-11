from datetime import datetime
import os

from django.shortcuts import render, redirect, reverse
from django.views.generic import View
from django.http.response import JsonResponse
from django.db import transaction
from dailyfresh.settings import BASE_DIR

from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo, OrderGoods
from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin

from alipay import AliPay

# Create your views here.
# 因为没有使用ajax post请求，所以这里可以使用LoginRequiredMixin做用户登录限制
class OrderPlaceView(LoginRequiredMixin, View):
    """提交订单页面显示"""
    def post(self, request):
        """提交订单页面显示"""
        # 获取参数,getlist()获取一个名字对应多个值
        sku_ids = request.POST.getlist('sku_ids')   # [1, 26]
        user = request.user

        # 校验参数
        if not sku_ids:
            # 跳转到购物车页面
            return redirect(reverse('cart:show'))

        # 遍历sku_ids获取用户要购买的商品信息
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        skus = []
        # 分别保存商品的总件数和总价格
        total = 0
        total_price = 0
        for sku_id in sku_ids:
            # 根据商品的id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            count = conn.hget(cart_key, sku_id)
            amount = sku.price * int(count)
            # 动态给sku增加属性
            sku.amount = amount
            sku.count = int(count)
            skus.append(sku)

            # 累加计算商品的总件数和总价格
            total += int(count)
            total_price += amount

        # 运费：实际开发的时候，属于一个子系统
        transit_price = 10  # 写死

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收件地址
        addrs = Address.objects.filter(user=user)

        # 返回应答
        sku_ids = ','.join(sku_ids)
        context = {'skus': skus, "total": total, 'total_price': total_price,
                   'transit_price': transit_price, 'total_pay': total_pay,
                   'addrs': addrs, 'sku_ids': sku_ids}
        return render(request, 'order/place_order.html', context=context)


# 前段传递的参数：地址id(addr_id)、支付方式（pay_method）、用户要购买的商品id字符串（sku_ids）
# mysql事务：一组sql操作，要么度成功，要么都失败
# 高并发：秒杀
# 支付宝支付
class OrderCommitView1(View):
    """订单创建"""
    @transaction.atomic()   # django显示控制事务
    def post(self, request):
        """订单创建"""
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 获取参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})
        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})
        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            #地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务
        # 用户每下一个订单，就需要向df_order_info表中加入一条记录；用户有几个商品，就需要向df_order_goods表中加入几条记录

        # 组织参数
        # 订单id：20171122181639+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置django事务点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info表中加入一条记录
            order = OrderInfo.objects.create(order_id=order_id, user=user, addr=addr,
                                     pay_method=pay_method, total_count=total_count,
                                     total_price=total_price, transit_price=transit_price)

            # todo: 用户有几个商品，就需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品的信息
                try:
                    # select * from fd_goods_sku where id = sku_id for update;   悲观锁
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)
                # todo: 判断商品的库存
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '库存不足'})
                # todo: 向df_order_goods表中加入几条记录
                OrderGoods.objects.create(order=order, sku=sku, count=count, price=sku.price)
                # todo: 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()
                # todo: 累加计算商品的总数和总价格
                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount
            # todo: 更新商品表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})
        # 提交事务
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车(redis)中的商品信息
        conn.hdel(cart_key, *sku_ids)
        # 返回应答
        return JsonResponse({'res': 5, 'message': '订单创建成功'})


class OrderCommitView(View):
    """订单创建"""

    @transaction.atomic()  # django显示控制事务
    def post(self, request):
        """订单创建"""
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 获取参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验参数
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})
        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHOD.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})
        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})

        # todo: 创建订单核心业务
        # 用户每下一个订单，就需要向df_order_info表中加入一条记录；用户有几个商品，就需要向df_order_goods表中加入几条记录

        # 组织参数
        # 订单id：20171122181639+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置django事务点
        save_id = transaction.savepoint()
        try:
            # todo: 向df_order_info表中加入一条记录
            order = OrderInfo.objects.create(order_id=order_id, user=user, addr=addr,
                                             pay_method=pay_method, total_count=total_count,
                                             total_price=total_price, transit_price=transit_price)

            # todo: 用户有几个商品，就需要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    # 获取商品的信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)
                    # todo: 判断商品的库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, 'errmsg': '库存不足'})

                    # todo: 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    # todo: 向df_order_goods表中加入几条记录， 乐观锁需要尝试3次，还是失败就返回响应
                    # update df_order_goods set stock=new_stock, sales=new_sales where id = sku_id and stock = orgin_stock
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        if i == 2:
                            # 尝试三次
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, 'errmsg': '下单失败2'})
                        continue

                    # todo: 向df_order_goods表中加入几条记录
                    OrderGoods.objects.create(order=order, sku=sku, count=count, price=sku.price)
                    # todo: 累加计算商品的总数和总价格
                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    # 跳出循环
                    break
            # todo: 更新商品表中的商品的总数量和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败1'})
        # 提交事务
        transaction.savepoint_commit(save_id)

        # todo: 清除用户购物车(redis)中的商品信息
        conn.hdel(cart_key, *sku_ids)
        # 返回应答
        return JsonResponse({'res': 5, 'message': '订单创建成功'})


# ajax post
# 前段传递的参数：订单ID(order_id)
class OrderPayVIew(View):
    """订单支付"""
    def post(self, request):
        """订单支付"""
        # 用户是否登录
        user = request.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=1,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务处理：使用Python sdk调用支付宝的支付接口
        app_private_key_string = open(os.path.join(BASE_DIR, "apps/order/alipay/app_private_key.pem")).read()
        alipay_public_key_string = open(os.path.join(BASE_DIR, 'apps/order/alipay/alipay_public_key.pem')).read()

        # 初始化
        alipay = AliPay(
            appid="2016102300746102",      # 应用的ID
            app_notify_url=None,           # 默认回调的url
            app_private_key_string=app_private_key_string,     # 应用的公钥
            alipay_public_key_string=alipay_public_key_string,  # 支付宝的公钥
            sign_type="RSA2",
            debug=True
        )

        # 如果你是 Python 3的用户，使用默认的字符串即可
        subject = "天天生鲜%s" % order_id

        total_pay = order.total_price + order.transit_price     # Decimal

        # 电脑网站支付，需要跳转到https://openapi.alipaydev.com/gateway.do? + order_string
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,    # 订单ID
            total_amount=str(total_pay),    # 支付总金额
            subject=subject,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回应答
        pay_url = "https://openapi.alipaydev.com/gateway.do?" + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})


# ajax post
# 前端传递参数：订单ID(order_id)
class OrderCheckView(View):
    """查看订单支付的结果"""
    def post(self, requset):
        # 用户是否登录
        user = requset.user
        if not user.is_authenticated:
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 接收参数
        order_id = requset.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单ID'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=1,
                                          order_status=1)
        except order.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务逻辑：查询订单支付的结果
        app_private_key_string = open(os.path.join(BASE_DIR, "apps/order/alipay/app_private_key.pem")).read()
        alipay_public_key_string = open(os.path.join(BASE_DIR, 'apps/order/alipay/alipay_public_key.pem')).read()
        # 初始化
        alipay = AliPay(
            appid="2016102300746102",  # 应用的ID
            app_notify_url=None,  # 默认回调的url
            app_private_key_string=app_private_key_string,  # 应用的公钥
            alipay_public_key_string=alipay_public_key_string,  # 支付宝的公钥
            sign_type="RSA2",
            debug=True
        )
        # 调用支付宝的查询接口
        while True:
            response = alipay.api_alipay_trade_query(out_trade_no=order_id)
            code = response.get('code')
            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 支付成功
                # 获取支付宝交易号
                # 更新订单状态
                order.trade_no = response.get("trade_no")
                order.order_status = 4
                order.save()
                # 返回结果
                return JsonResponse({'res': 3, 'message': '支付成功'})
            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 等待买家付款
                # 业务处理失败，可能一会就会成功
                import time
                time.sleep(5)
                continue
            else:
                # 支付出错
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})

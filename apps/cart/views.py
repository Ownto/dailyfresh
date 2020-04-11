from django.shortcuts import render
from django.views.generic import View
from django_redis import get_redis_connection
from django.http import JsonResponse

from goods.models import GoodsSKU
from utils.mixin import LoginRequiredMixin

# Create your views here.
# 获取商品到购物车
# 请求方式： AJAX POST
# 1、如果需要对数据进行修改(新增、删除、更新)时，使用POST
# 2、如果只涉及到数据的获取，使用GET
# 请求参数： 商品ID、商品数量
# ajax发起的请求都在后台，在浏览器中看不到效果


# /cart/add
class CartView(View):
    """购物车记录添加"""
    def post(self, request):
        # 接受数据
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数量出错'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 检验商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # 业务处理：添加购物车记录
        conn = get_redis_connection('default')
        cart_key = "cart_%d" % user.id
        # 如果sku_id在hash中不存在，hget返回一个None
        cart_count = conn.hget(cart_key, sku_id)
        if cart_count:
            count += int(cart_count)
        # hset在sku_id不存在时，是新增，存在时就是更新
        conn.hset(cart_key, sku_id, count)

        # 计算购物车中商品的条目数
        total_count = conn.hlen(cart_key)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'errmsg': '添加成功'})


class CartInfoView(LoginRequiredMixin, View):
    """购物车页面显示"""
    def get(self, request):
        """显示"""
        # 获取登录的用户名
        user = request.user
        # 获取用户购物车中的商品信息
        cart_key = "cart_%d" % user.id
        conn = get_redis_connection('default')
        # {'商品id': '商品数量'}
        cart_dict = conn.hgetall(cart_key)

        skus = []
        # 保存用户购物车中商品的总数目和总价格
        total_count = 0
        total_price = 0
        for sku_id, count in cart_dict.items():
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)
            # 动态给sku增加一个属性，保存商品的小计
            sku.amount = amount
            # 动态给sku增加一个属性，保存购物车中对应商品的数量
            sku.count = int(count)
            # 添加
            skus.append(sku)

            # 累加计算商品的总数目和总价格
            total_count += int(count)
            total_price += amount

        context = {"skus": skus, "total_count": total_count,
                   "total_price": total_price}
        return render(request, "cart/cart.html", context=context)


# 更新购物车记录
# 请求方式： ajax post
# 前端需要传递的参数：商品id(sku_id), 更新的商品数量(count)
# cart/update
class CartUpdateView(View):
    """购物车记录更新"""
    def post(self, request):
        """购物车记录更新"""

        # 参数的接收
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数量出错'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 检验商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # 业务逻辑处理：购物车记录更新
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        conn.hset(cart_key, sku_id, count)

        # 计算用户购物车中商品的总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)


        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '更新成功', 'total_count': total_count})


# 删除购物车记录
# 采用ajax post请求
# 前端需要传递的参数：商品的id(sku_id)
# /cart/delete
class CartDeleteView(View):
    """购物车记录删除"""
    def post(self, request):
        """购物车记录删除"""
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})
        # 接收参数
        sku_id = request.POST.get('sku_id')
        # 校验数据

        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务逻辑处理，删除购物车记录
        cart_key = "cart_%d" % user.id
        conn = get_redis_connection('default')
        conn.hdel(cart_key, sku_id)

        # 计算用户购物车中商品的总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'message': '删除成功'})

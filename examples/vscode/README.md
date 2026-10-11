# Workspace VS Code mẫu: thống kê bằng code

1. **Cài CLI và tạo profile** (một lần):
   ```sh
   odoo-cli profile set --name asao-hq --endpoint https://… --database asao-hq --login <email> --protocol json2
   ```
   Mật khẩu hoặc API key nằm ở biến môi trường `AERP_CREDENTIAL_ASAO_HQ`, hoặc keyring, không bao giờ nằm
   trong notebook. Muốn in PDF thì thêm mật khẩu web: `AERP_CREDENTIAL_ASAO_HQ_WEB`.
2. **Cài SDK** vào môi trường Python của workspace:
   ```sh
   pip install -e 'packages/sdk-python[pandas]'
   ```
3. **Mở thư mục này trong VS Code**, cài các extension được gợi ý (Python, Jupyter), chọn kernel Python, rồi
   chạy `thong-ke.ipynb`. Đặt `ASAO_ERP_PROFILE` nếu profile không tên `asao-hq`.

Quy tắc:
- Client mặc định **chỉ đọc**.
- **Xoá output** của notebook trước khi commit. Tệp CSV và PDF đã nằm trong `.gitignore`.
- Không chép dữ liệu cá nhân (số điện thoại, email, lương) ra ngoài máy.

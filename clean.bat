@echo off
cd /d "%~dp0"
del /q dg_*.png dg_*.json *_lit.png *_cut.png *_cut.png.sig fx_*.png 2>nul
if exist image del /q image\dg_*.png image\dg_*.json image\*_lit.png image\*_cut.png image\fx_*.png 2>nul
echo 삭제 완료
pause
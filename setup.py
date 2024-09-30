import setuptools

setuptools.setup(
    name='S15qkd',
    version='0.2',
    description='QKD process controller. Python wrapper for qcrypto.',
    url='https://s-fifteen.com/',
    author='Mathias Seidler;',
    author_email='',
    license='MIT',
    packages=setuptools.find_packages(),
    install_requires=['pyserial', 'numpy', 'psutil', 'dataclasses'],
)

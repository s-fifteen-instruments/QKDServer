import matplotlib.pyplot as plt
import matplotlib.dates
import numpy as np

data = np.load('epoch_analy.npy', allow_pickle=True)
data = data.flatten()[0]
data_run = (data['date_int'][-1]-data['date_int'][0])

dates = matplotlib.dates.date2num(data['date'])
plt.plot_date(dates, data['ingested_bits'])
plt.xlabel('Date')
plt.ylabel('Number of ingested_bits')
plt.title(f"Final bits over { data_run/60//60:.2f} hours")
plt.show()


delta_t = np.diff(data['date_int'])
plt.plot_date(dates[1:], delta_t)
plt.plot(plt.xlim(),(300,300), '-r')
plt.xlabel('Date')
plt.ylabel('delta t (s)')
plt.title('Time between each final key epoch')
plt.grid()
plt.show()

average_bit_rate = sum(data['ingested_bits'])/data_run

print(f'Average bit rate from first key generation {average_bit_rate:.1f} bps')
